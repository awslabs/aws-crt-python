/*
 * Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *  http://aws.amazon.com/apache2.0
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */
#include "http.h"

#include "io.h"

#include <aws/common/array_list.h>
#include <aws/http/connection.h>
#include <aws/http/request_response.h>
#include <aws/io/socket.h>

static const char *s_capsule_name_http_connection = "aws_http_connection";

/**
 * Lifetime notes:
 * - If connect() reports immediate failure, binding can be destroyed.
 * - If on_connection_setup reports failure, binding can be destroyed.
 * - Otherwise, binding cannot be destroyed until BOTH release() has been called AND on_connection_shutdown has fired.
 */
struct http_connection_binding {
    struct aws_http_connection *native;

    bool release_called;
    bool shutdown_called;

    /* Setup callback, reference cleared after invoking */
    PyObject *on_setup;

    /* Shutdown future, reference cleared after setting result */
    PyObject *shutdown_future;

    /* Dependencies that must outlive this */
    PyObject *bootstrap;
    PyObject *tls_ctx;
};

static void s_connection_destroy(struct http_connection_binding *connection) {
    Py_XDECREF(connection->on_setup);
    Py_XDECREF(connection->shutdown_future);
    Py_XDECREF(connection->bootstrap);
    Py_XDECREF(connection->tls_ctx);

    aws_mem_release(aws_py_get_allocator(), connection);
}

struct aws_http_connection *aws_py_get_http_connection(PyObject *connection) {
    struct aws_http_connection *native = NULL;

    PyObject *capsule = PyObject_GetAttrString(connection, "_binding");
    if (capsule) {
        struct http_connection_binding *binding = PyCapsule_GetPointer(capsule, s_capsule_name_http_connection);
        if (binding) {
            native = binding->native;
            AWS_FATAL_ASSERT(native);
        }
        Py_DECREF(capsule);
    }

    return native;
}

static void s_connection_release(struct http_connection_binding *connection) {
    AWS_FATAL_ASSERT(!connection->release_called);
    connection->release_called = true;

    bool destroy_after_release = connection->shutdown_called;

    aws_http_connection_release(connection->native);

    if (destroy_after_release) {
        s_connection_destroy(connection);
    }
}

static void s_connection_capsule_destructor(PyObject *capsule) {
    struct http_connection_binding *connection = PyCapsule_GetPointer(capsule, s_capsule_name_http_connection);
    s_connection_release(connection);
}

static void s_on_connection_shutdown(struct aws_http_connection *native_connection, int error_code, void *user_data) {
    (void)native_connection;
    struct http_connection_binding *connection = user_data;
    AWS_FATAL_ASSERT(!connection->shutdown_called);

    PyGILState_STATE state = PyGILState_Ensure();

    connection->shutdown_called = true;

    bool destroy_after_shutdown = connection->release_called;

    /* Set result of shutdown_future, then clear our reference to shutdown_future. */
    PyObject *result = PyObject_CallMethod(connection->shutdown_future, "set_result", "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
        /* Note: We used to FATAL_ASSERT here, since this future really must succeed.
         * But the assert would trigger occasionally during application shutdown, so removing it for now. */
    }
    Py_CLEAR(connection->shutdown_future);

    if (destroy_after_shutdown) {
        s_connection_destroy(connection);
    }

    PyGILState_Release(state);
}

static void s_on_client_connection_setup(
    struct aws_http_connection *native_connection,
    int error_code,
    void *user_data) {

    struct http_connection_binding *connection = user_data;
    AWS_FATAL_ASSERT((native_connection != NULL) ^ error_code);
    AWS_FATAL_ASSERT(connection->on_setup);

    connection->native = native_connection;

    PyGILState_STATE state = PyGILState_Ensure();

    /* If setup was successful, encapsulate binding so we can pass it to python */
    PyObject *capsule = NULL;
    if (!error_code) {
        capsule = PyCapsule_New(connection, s_capsule_name_http_connection, s_connection_capsule_destructor);
        if (!capsule) {
            error_code = AWS_ERROR_UNKNOWN;
        }
    }

    /* Invoke on_setup, then clear our reference to it */
    PyObject *result = PyObject_CallFunction(connection->on_setup, "(Ni)", capsule ? capsule : Py_None, error_code);
    if (!result) {
        /* This function must succeed. Can't leave a Future incomplete. */
        PyErr_WriteUnraisable(PyErr_Occurred());
        AWS_FATAL_ASSERT(0);
    }

    Py_DECREF(result);
    Py_CLEAR(connection->on_setup);

    if (native_connection) {
        /* Connection exists, but failed to create capsule. Release connection, which eventually destroys binding */
        if (!capsule) {
            s_connection_release(connection);
        }
    } else {
        /* Connection failed its setup, destroy binding now */
        s_connection_destroy(connection);
    }

    /* Py_XDECREF(capsule); ??? Not sure why this deletes capsule. It's referenced by HttpConnection._binding !!! */

    Py_XDECREF(result);
    PyGILState_Release(state);
}

PyObject *aws_py_http_client_connection_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py;
    PyObject *on_connection_setup_py;
    PyObject *shutdown_future_py;
    const char *host_name;
    Py_ssize_t host_name_len;
    uint16_t port_number;
    PyObject *socket_options_py;
    PyObject *tls_options_py;

    if (!PyArg_ParseTuple(
            args,
            "OOOs#HOO",
            &bootstrap_py,
            &on_connection_setup_py,
            &shutdown_future_py,
            &host_name,
            &host_name_len,
            &port_number,
            &socket_options_py,
            &tls_options_py)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct http_connection_binding *connection = aws_mem_calloc(allocator, 1, sizeof(struct http_connection_binding));
    if (!connection) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur */

    struct aws_tls_connection_options *tls_options = NULL;
    if (tls_options_py != Py_None) {
        tls_options = aws_py_get_tls_connection_options(tls_options_py);
        if (!tls_options) {
            goto error;
        }

        connection->tls_ctx = PyObject_GetAttrString(tls_options_py, "tls_ctx"); /* Creates new reference */
        if (!connection->tls_ctx) {
            goto error;
        }
    }

    struct aws_socket_options socket_options;
    if (!aws_py_socket_options_init(&socket_options, socket_options_py)) {
        goto error;
    }

    struct aws_http_client_connection_options http_options = {
        .self_size = sizeof(http_options),
        .bootstrap = bootstrap,
        .tls_options = tls_options,
        .allocator = allocator,
        .user_data = connection,
        .host_name = aws_byte_cursor_from_array((const uint8_t *)host_name, host_name_len),
        .port = port_number,
        .initial_window_size = SIZE_MAX,
        .socket_options = &socket_options,
        .on_setup = s_on_client_connection_setup,
        .on_shutdown = s_on_connection_shutdown,
    };

    connection->on_setup = on_connection_setup_py;
    Py_INCREF(connection->on_setup);
    connection->shutdown_future = shutdown_future_py;
    Py_INCREF(connection->shutdown_future);
    connection->bootstrap = bootstrap_py;
    Py_INCREF(connection->bootstrap);

    if (aws_http_client_connect(&http_options)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    Py_RETURN_NONE;

error:
    s_connection_destroy(connection);
    return NULL;
}

PyObject *aws_py_http_connection_close(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) {
        return NULL;
    }

    struct http_connection_binding *connection = PyCapsule_GetPointer(capsule, s_capsule_name_http_connection);
    if (!connection) {
        return NULL;
    }

    aws_http_connection_close(connection->native);
    Py_RETURN_NONE;
}

PyObject *aws_py_http_connection_is_open(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) {
        return NULL;
    }

    struct http_connection_binding *connection = PyCapsule_GetPointer(capsule, s_capsule_name_http_connection);
    if (!connection) {
        return NULL;
    }

    if (aws_http_connection_is_open(connection->native)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}
