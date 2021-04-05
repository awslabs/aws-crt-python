/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "http.h"

#include "io.h"

#include <aws/common/array_list.h>
#include <aws/http/connection.h>
#include <aws/http/proxy.h>
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

    /* Shutdown callback, reference cleared after setting result */
    PyObject *on_shutdown;

    /* Dependencies that must outlive this */
    PyObject *bootstrap;
    PyObject *tls_ctx;
};

static void s_connection_destroy(struct http_connection_binding *connection) {
    Py_XDECREF(connection->on_setup);
    Py_XDECREF(connection->on_shutdown);
    Py_XDECREF(connection->bootstrap);
    Py_XDECREF(connection->tls_ctx);

    aws_mem_release(aws_py_get_allocator(), connection);
}

struct aws_http_connection *aws_py_get_http_connection(PyObject *connection) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        connection, s_capsule_name_http_connection, "HttpConnectionBase", http_connection_binding);
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

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    connection->shutdown_called = true;

    bool destroy_after_shutdown = connection->release_called;

    /* Invoke on_shutdown, then clear our reference to it */
    PyObject *result = PyObject_CallFunction(connection->on_shutdown, "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_CLEAR(connection->on_shutdown);

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

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    enum aws_http_version http_version = AWS_HTTP_VERSION_UNKNOWN;
    /* If setup was successful, encapsulate binding so we can pass it to python */
    PyObject *capsule = NULL;
    if (!error_code) {
        capsule = PyCapsule_New(connection, s_capsule_name_http_connection, s_connection_capsule_destructor);
        if (!capsule) {
            error_code = AWS_ERROR_UNKNOWN;
        }
        http_version = aws_http_connection_get_version(native_connection);
    }

    /* Invoke on_setup, then clear our reference to it */
    PyObject *result =
        PyObject_CallFunction(connection->on_setup, "(Oii)", capsule ? capsule : Py_None, error_code, http_version);

    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

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

    Py_XDECREF(capsule);
    Py_XDECREF(result);
    PyGILState_Release(state);
}

PyObject *aws_py_http_client_connection_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py;
    PyObject *on_connection_setup_py;
    PyObject *on_shutdown_py;
    const char *host_name;
    Py_ssize_t host_name_len;
    uint16_t port_number;
    PyObject *socket_options_py;
    PyObject *tls_options_py;
    PyObject *proxy_options_py;

    if (!PyArg_ParseTuple(
            args,
            "OOOs#HOOO",
            &bootstrap_py,
            &on_connection_setup_py,
            &on_shutdown_py,
            &host_name,
            &host_name_len,
            &port_number,
            &socket_options_py,
            &tls_options_py,
            &proxy_options_py)) {
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
        if (!connection->tls_ctx || connection->tls_ctx == Py_None) {
            PyErr_SetString(PyExc_TypeError, "tls_connection_options.tls_ctx is invalid");
            goto error;
        }
    }

    struct aws_socket_options socket_options;
    if (!aws_py_socket_options_init(&socket_options, socket_options_py)) {
        goto error;
    }

    /* proxy options are optional */
    struct aws_http_proxy_options proxy_options_storage;
    struct aws_http_proxy_options *proxy_options = NULL;
    if (proxy_options_py != Py_None) {
        proxy_options = &proxy_options_storage;
        if (!aws_py_http_proxy_options_init(proxy_options, proxy_options_py)) {
            goto error;
        }
    }

    struct aws_http_client_connection_options http_options = {
        .self_size = sizeof(http_options),
        .bootstrap = bootstrap,
        .tls_options = tls_options,
        .proxy_options = proxy_options,
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
    connection->on_shutdown = on_shutdown_py;
    Py_INCREF(connection->on_shutdown);
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
