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
#include "http_client_connection.h"

#include "io.h"

#include <aws/io/socket.h>

const char *s_capsule_name_http_client_connection = "aws_http_client_connection";

struct py_http_connection {
    struct aws_allocator *allocator;
    struct aws_http_connection *connection;
    PyObject *capsule;
    PyObject *on_connection_setup;
    PyObject *on_connection_shutdown;
    bool destructor_called;
    bool shutdown_called;
};

static void s_http_client_connection_destructor(PyObject *http_connection_capsule) {
    struct py_http_connection *http_connection = PyCapsule_GetPointer(http_connection_capsule, s_capsule_name_http_client_connection);
    assert(http_connection);

    http_connection->destructor_called = true;
    if (http_connection->connection) {

        if (aws_http_connection_is_open(http_connection->connection)) {
            aws_http_connection_close(http_connection->connection);
        }

        aws_http_connection_release(http_connection->connection);
        http_connection->connection = NULL;
    }

    if (http_connection->shutdown_called) {
        aws_mem_release(http_connection->allocator, http_connection);
    }
}

static void s_on_client_connection_setup(
        struct aws_http_connection *connection,
        int error_code,
        void *user_data) {

    struct py_http_connection *py_connection = user_data;

    fprintf(stderr, "Completed connection with error %d\n", error_code);
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *result = NULL;
    PyObject* capsule = NULL;

    if (!error_code) {
        py_connection->connection = connection;
        capsule = PyCapsule_New(py_connection, s_capsule_name_http_client_connection, s_http_client_connection_destructor);
        py_connection->capsule = capsule;
    } else {
        aws_mem_release(py_connection->allocator, py_connection);
    }
    fprintf(stderr, "Calling function\n");

    result = PyObject_CallFunction(py_connection->on_connection_setup, "(Oi)", capsule, error_code);
    fprintf(stderr, "function called\n");

    Py_XDECREF(result);
    PyGILState_Release(state);
    fprintf(stderr, "invoked callback and relaesed gil\n");

}

static void s_on_client_connection_shutdown(
        struct aws_http_connection *connection,
        int error_code,
        void *user_data) {
    (void)connection;

    struct py_http_connection *py_connection = user_data;

    PyGILState_STATE state = PyGILState_Ensure();
    py_connection->shutdown_called = true;

    if (!py_connection->destructor_called) {
        PyObject *result = PyObject_CallFunction(py_connection->on_connection_shutdown, "(Oi)", py_connection->capsule,
                                                 error_code);
        Py_XDECREF(result);
    } else {
        aws_mem_release(py_connection->allocator, py_connection);
    }

    PyGILState_Release(state);
}


PyObject *aws_py_http_client_connection_create(PyObject *self, PyObject *args) {
    (void)self;

    struct py_http_connection *py_connection = NULL;
    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    PyObject *bootstrap_capsule = NULL;
    PyObject *on_connection_shutdown = NULL;
    PyObject *on_connection_setup = NULL;
    const char *host_name = NULL;
    Py_ssize_t host_name_len = 0;
    uint16_t port_number = 0;
    Py_ssize_t initial_window_size = PY_SSIZE_T_MAX;
    PyObject *py_socket_options = NULL;
    PyObject *tls_conn_options_capsule = NULL;

    if (!PyArg_ParseTuple(args, "OOOs#HOO", &bootstrap_capsule, &on_connection_setup,
            &on_connection_shutdown, &host_name, &host_name_len, &port_number,
            &py_socket_options, &tls_conn_options_capsule)) {
        goto error;
    }

    if (!bootstrap_capsule || !PyCapsule_CheckExact(bootstrap_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }

    if (tls_conn_options_capsule && !PyCapsule_CheckExact(tls_conn_options_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }

    if (!(host_name &&  py_socket_options && on_connection_setup && on_connection_shutdown)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }

    struct aws_client_bootstrap *bootstrap = PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_client_bootstrap);
    if (!bootstrap) {
        goto error;
    }

    struct aws_tls_connection_options *connection_options = NULL;

    if (tls_conn_options_capsule) {
        connection_options = PyCapsule_GetPointer(tls_conn_options_capsule, s_capsule_name_tls_conn_options);
    }

    py_connection = aws_mem_acquire(allocator, sizeof(struct py_http_connection));
    if (!py_connection) {
        PyErr_SetAwsLastError();
        goto error;
    }
    AWS_ZERO_STRUCT(*py_connection);

    struct aws_socket_options socket_options;
    AWS_ZERO_STRUCT(socket_options);
    PyObject *sock_domain = PyObject_GetAttrString(py_socket_options, "domain");
    if (sock_domain) {
        socket_options.domain = (enum aws_socket_domain)PyIntEnum_AsLong(sock_domain);
    }

    PyObject *sock_type = PyObject_GetAttrString(py_socket_options, "type");
    if (sock_type) {
        socket_options.type = (enum aws_socket_type)PyIntEnum_AsLong(sock_type);
    }

    PyObject *connect_timeout_ms = PyObject_GetAttrString(py_socket_options, "connect_timeout_ms");
    if (connect_timeout_ms) {
        socket_options.connect_timeout_ms = (uint32_t)PyLong_AsLong(connect_timeout_ms);
    }

    PyObject *keep_alive = PyObject_GetAttrString(py_socket_options, "keep_alive");
    if (keep_alive) {
        socket_options.keepalive = (bool)PyObject_IsTrue(keep_alive);
    }

    PyObject *keep_alive_interval = PyObject_GetAttrString(py_socket_options, "keep_alive_interval_secs");
    if (keep_alive_interval) {
        socket_options.keep_alive_interval_sec = (uint16_t)PyLong_AsLong(keep_alive_interval);
    }

    PyObject *keep_alive_timeout = PyObject_GetAttrString(py_socket_options, "keep_alive_timeout_secs");
    if (keep_alive_timeout) {
        socket_options.keep_alive_timeout_sec = (uint16_t)PyLong_AsLong(keep_alive_timeout);
    }

    PyObject *keep_alive_max_probes = PyObject_GetAttrString(py_socket_options, "keep_alive_max_probes");
    if (keep_alive_timeout) {
        socket_options.keep_alive_max_failed_probes = (uint16_t)PyLong_AsLong(keep_alive_max_probes);
    }

    if (!PyCallable_Check(on_connection_setup)) {
        PyErr_SetString(PyExc_TypeError, "on_connection_setup is invalid");
        goto error;
    }

    Py_INCREF(on_connection_setup);
    py_connection->on_connection_setup = on_connection_setup;

    if (!PyCallable_Check(on_connection_shutdown)) {
        PyErr_SetString(PyExc_TypeError, "on_connection_shutdown is invalid");
        goto error;
    }

    Py_INCREF(on_connection_shutdown);
    py_connection->on_connection_shutdown = on_connection_shutdown;

    py_connection->allocator = allocator;
    py_connection->on_connection_setup = on_connection_setup;
    py_connection->on_connection_shutdown = on_connection_shutdown;

    struct aws_http_client_connection_options options;
    AWS_ZERO_STRUCT(options);
    options.self_size = sizeof(options);
    options.bootstrap = bootstrap;
    options.tls_options = connection_options;
    options.allocator = allocator;
    options.user_data = py_connection;
    options.host_name = aws_byte_cursor_from_array((const uint8_t *)host_name, host_name_len);
    options.port = port_number;
    options.initial_window_size = initial_window_size;
    options.socket_options = &socket_options;
    options.on_setup = s_on_client_connection_setup;
    options.on_shutdown = s_on_client_connection_shutdown;

    if (aws_http_client_connect(&options)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    Py_RETURN_NONE;

error:
    if (py_connection) {
        aws_mem_release(allocator, py_connection);
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_client_connection_close(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *http_impl = NULL;

    if (PyArg_ParseTuple(args, "O", &http_impl)) {
        struct py_http_connection *http_connection = PyCapsule_GetPointer(http_impl, s_capsule_name_http_client_connection);
        assert(http_connection);

        if (http_connection->connection) {
            aws_http_connection_close(http_connection->connection);
        }
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_client_connection_is_open(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *http_impl = NULL;

    if (PyArg_ParseTuple(args, "O", &http_impl)) {
        struct py_http_connection *http_connection = PyCapsule_GetPointer(http_impl, s_capsule_name_http_client_connection);
        assert(http_connection);

        if (http_connection->connection && aws_http_connection_is_open(http_connection->connection)) {
            Py_RETURN_TRUE;
        }
    }

    Py_RETURN_FALSE;
}
