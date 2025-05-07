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
    /* Reference to python object that reference to other related python object to keep it alive */
    PyObject *py_core;

    bool release_called;
    bool shutdown_called;
};

static void s_connection_destroy(struct http_connection_binding *connection) {
    Py_XDECREF(connection->py_core);

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
    PyObject *result = PyObject_CallMethod(connection->py_core, "_on_shutdown", "(i)", error_code);

    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

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

    PyObject *result = PyObject_CallMethod(
        connection->py_core, "_on_connection_setup", "(Oii)", capsule ? capsule : Py_None, error_code, http_version);

    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

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
    PyGILState_Release(state);
}

/* Function to convert Python list of Http2Setting to C array of aws_http2_setting */
static int s_convert_http2_settings(
    PyObject *initial_settings_py,
    struct aws_allocator *allocator,
    struct aws_http2_setting **out_settings,
    size_t *out_size) {
    Py_ssize_t py_list_size = PyList_Size(initial_settings_py);
    if (py_list_size == 0) {
        *out_size = 0;
        *out_settings = NULL;
        return AWS_OP_SUCCESS;
    }

    *out_settings = aws_mem_calloc(allocator, py_list_size, sizeof(struct aws_http2_setting));

    for (Py_ssize_t i = 0; i < py_list_size; i++) {
        PyObject *setting_py = PyList_GetItem(initial_settings_py, i);

        /* Get id attribute */
        enum aws_http2_settings_id id = PyObject_GetAttrAsIntEnum(setting_py, "Http2Setting", "id");
        if (PyErr_Occurred()) {
            goto error;
        }

        /* Get value attribute */
        uint32_t value = PyObject_GetAttrAsUint32(setting_py, "Http2Setting", "value");
        if (PyErr_Occurred()) {
            goto error;
        }
        (*out_settings)[i].id = id;
        (*out_settings)[i].value = value;
    }

    *out_size = (size_t)py_list_size;
    return AWS_OP_SUCCESS;
error:
    *out_size = 0;
    aws_mem_release(allocator, out_settings);
    *out_settings = NULL;
    return AWS_OP_ERR;
}

static void s_http2_on_remote_settings_change(
    struct aws_http_connection *http2_connection,
    const struct aws_http2_setting *settings_array,
    size_t num_settings,
    void *user_data) {
    (void)http2_connection;
    struct http_connection_binding *connection = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    // Create a new list to hold tuples
    PyObject *py_settings_list = PyList_New(num_settings);
    if (!py_settings_list) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        return;
    }
    for (size_t i = 0; i < num_settings; i++) {
        PyObject *tuple = Py_BuildValue("(iI)", settings_array[i].id, settings_array[i].value);
        if (!tuple) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            goto done;
        }
        PyList_SetItem(py_settings_list, i, tuple); /* steals reference to tuple */
    }
    PyObject *result = PyObject_CallMethod(connection->py_core, "_on_remote_settings_changed", "(O)", py_settings_list);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto done;
    }
    Py_DECREF(result);
done:
    Py_XDECREF(py_settings_list);
    PyGILState_Release(state);
}

PyObject *aws_py_http_client_connection_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py;
    const char *host_name;
    Py_ssize_t host_name_len;
    uint32_t port_number;
    PyObject *socket_options_py;
    PyObject *tls_options_py;
    PyObject *proxy_options_py;
    PyObject *py_core;

    if (!PyArg_ParseTuple(
            args,
            "Os#IOOOO",
            &bootstrap_py,
            &host_name,
            &host_name_len,
            &port_number,
            &socket_options_py,
            &tls_options_py,
            &proxy_options_py,
            &py_core)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct http_connection_binding *connection = aws_mem_calloc(allocator, 1, sizeof(struct http_connection_binding));
    /* From hereon, we need to clean up if errors occur */
    struct aws_http2_setting *http2_settings = NULL;
    size_t http2_settings_count = 0;
    struct aws_http2_connection_options http2_options = {0};

    struct aws_tls_connection_options *tls_options = NULL;
    if (tls_options_py != Py_None) {
        tls_options = aws_py_get_tls_connection_options(tls_options_py);
        if (!tls_options) {
            goto error;
        }
    }

    struct aws_socket_options socket_options;
    if (!aws_py_socket_options_init(&socket_options, socket_options_py)) {
        goto done;
    }

    if (initial_settings_py != Py_None) {
        /* Get the array from the pylist */
        if (s_convert_http2_settings(initial_settings_py, allocator, &http2_settings, &http2_settings_count)) {
            goto done;
        }
        http2_options.initial_settings_array = http2_settings;
        http2_options.num_initial_settings = http2_settings_count;
    }
    if (on_remote_settings_changed_py != Py_None) {
        http2_options.on_remote_settings_change = s_http2_on_remote_settings_change;
    }

    /* proxy options are optional */
    struct aws_http_proxy_options proxy_options_storage;
    struct aws_http_proxy_options *proxy_options = NULL;
    if (proxy_options_py != Py_None) {
        proxy_options = &proxy_options_storage;
        if (!aws_py_http_proxy_options_init(proxy_options, proxy_options_py)) {
            goto done;
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
        .http2_options = &http2_options,
    };

    connection->py_core = py_core;
    Py_INCREF(connection->py_core);

    if (aws_http_client_connect(&http_options)) {
        PyErr_SetAwsLastError();
        goto done;
    }
    success = true;

done:
    if (http2_settings) {
        aws_mem_release(allocator, http2_settings);
    }
    if (!success) {
        s_connection_destroy(connection);
        return NULL;
    }
    Py_RETURN_NONE;
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
