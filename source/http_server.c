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
#include "http_server.h"

#include "io.h"

#include <aws/common/array_list.h>
#include <aws/http/request_response.h>
#include <aws/http/server.h>
#include <aws/io/socket.h>
#include <aws/io/stream.h>

const char *s_capsule_name_http_server = "aws_http_server";
const char *s_capsule_name_http_server_connection = "aws_http_server_connection";

struct py_http_server {
    struct aws_allocator *allocator;
    struct aws_http_server *server;
    PyObject *capsule;
    PyObject *on_incoming_connection;
    PyObject *on_destroy_complete;
    bool destructor_called;
    bool shutdown_called;
};

struct py_http_server_connection {
    struct aws_allocator *allocator;
    struct aws_http_connection *connection;
    PyObject *capsule;
    PyObject *on_incoming_request;
    PyObject *on_shutdown;
    bool destructor_called;
    bool shutdown_called;
};

static void s_http_server_connection_destructor(PyObject *http_server_conn_capsule){
    struct py_http_server_connection *http_connection =
        PyCapsule_GetPointer(http_server_conn_capsule, s_capsule_name_http_server_connection);
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

static void s_on_incoming_connection(
    struct aws_http_server *server,
    struct aws_http_connection *connection,
    int error_code,
    void *user_data) {

    struct py_http_server *py_server = user_data;
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *result = NULL;
    PyObject *connection_capsule = NULL;

    PyObject *on_incoming_conn_cb = py_server->on_incoming_connection;

    struct py_http_server_connection *py_connection = NULL;
    py_connection = aws_mem_acquire(py_server->allocator, sizeof(struct py_http_server_connection));
    py_connection->allocator = py_server->allocator;
    if (!error_code) {
        py_connection->connection = connection;
        connection_capsule =
            PyCapsule_New(py_connection, s_capsule_name_http_server_connection, s_http_server_connection_destructor);
        py_connection->capsule = connection_capsule;
    } else {
        aws_mem_release(py_connection->allocator, py_connection);
    }

    result = PyObject_CallFunction(on_incoming_conn_cb, "(NNi)", py_server->capsule, connection_capsule, error_code);

    Py_DECREF(on_incoming_conn_cb);
    Py_XDECREF(result);

    PyGILState_Release(state);
}

PyObject *aws_py_http_server_create(PyObject *self, PyObject *args) {
    (void)self;

    struct py_http_server *py_server = NULL;
    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    PyObject *bootstrap_capsule = NULL;
    PyObject *on_incoming_connection = NULL;
    PyObject *on_destroy_complete = NULL;
    const char *host_name = NULL;
    Py_ssize_t host_name_len = 0;
    uint16_t port_number = 0;
    Py_ssize_t initial_window_size = PY_SSIZE_T_MAX;
    PyObject *py_socket_options = NULL;
    PyObject *tls_conn_options_capsule = NULL;

    if (!PyArg_ParseTuple(
            args,
            "OOOs#HOO",
            &bootstrap_capsule,
            &on_incoming_connection,
            &on_destroy_complete,
            &host_name,
            &host_name_len,
            &port_number,
            &py_socket_options,
            &tls_conn_options_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }

    if (!bootstrap_capsule || !PyCapsule_CheckExact(bootstrap_capsule)) {
        PyErr_SetString(PyExc_ValueError, "bootstrap is invalid");
        goto error;
    }

    if (tls_conn_options_capsule && tls_conn_options_capsule != Py_None &&
        !PyCapsule_CheckExact(tls_conn_options_capsule)) {
        PyErr_SetString(PyExc_ValueError, "tls connection options is invalid");
        goto error;
    }

    if (!host_name) {
        PyErr_SetString(PyExc_ValueError, "host_name is a required argument");
        goto error;
    }

    if (!py_socket_options || py_socket_options == Py_None) {
        PyErr_SetString(PyExc_ValueError, "socket_options is a required argument");
        goto error;
    }

    if (!on_incoming_connection || on_incoming_connection == Py_None) {
        PyErr_SetString(PyExc_ValueError, "on_incoming_connection callback is required");
        goto error;
    }

    struct aws_server_bootstrap *bootstrap = PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_server_bootstrap);
    if (!bootstrap) {
        PyErr_SetString(PyExc_ValueError, "the bootstrap capsule has an invalid pointer");
        goto error;
    }

    struct aws_tls_connection_options *connection_options = NULL;

    if (tls_conn_options_capsule != Py_None) {
        connection_options = PyCapsule_GetPointer(tls_conn_options_capsule, s_capsule_name_tls_conn_options);
    }

    py_server = aws_mem_acquire(allocator, sizeof(struct py_http_server));
    if (!py_server) {
        PyErr_SetAwsLastError();
        goto error;
    }
    AWS_ZERO_STRUCT(*py_server);

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

    if (!PyCallable_Check(on_incoming_connection)) {
        PyErr_SetString(PyExc_TypeError, "on_incoming_connection is invalid");
        goto error;
    }

    Py_XINCREF(on_incoming_connection);
    py_server->on_incoming_connection = on_incoming_connection;

    py_server->on_destroy_complete = NULL;
    if (on_destroy_complete && on_destroy_complete != Py_None) {
        if (!PyCallable_Check(on_destroy_complete)) {
            PyErr_SetString(PyExc_TypeError, "on_destroy_complete is invalid");
            goto error;
        }
        Py_XINCREF(on_destroy_complete);
        py_server->on_destroy_complete = on_destroy_complete;
    }

    py_server->allocator = allocator;

    struct aws_http_server_options options;
    AWS_ZERO_STRUCT(options);
    options.self_size = sizeof(options);
    options.bootstrap = bootstrap;
    options.tls_options = connection_options;
    options.allocator = allocator;
    options.server_user_data = py_server;
    struct aws_socket_endpoint endpoint;
    AWS_ZERO_STRUCT(endpoint);

    snprintf(endpoint.address, host_name_len, host_name);
    endpoint.port = port_number;
    options.endpoint = &endpoint;
    options.on_incoming_connection = s_on_incoming_connection;
    options.on_destroy_complete = s_on_destroy_complete;
    py_server->server = aws_http_server_new(&options);
    PyObject *capsule = NULL;
    if(py_server->server){
        /* success */
        capsule =
            PyCapsule_New(py_server, s_capsule_name_http_server, s_http_server_destructor);
        py_server->capsule = capsule;
    }
    else{
        aws_mem_release(py_server->allocator, py_server);
    }
    return capsule;
error:
    if(py_server){
        aws_mem_release(py_server->allocator, py_server);
    }
    return NULL;
}