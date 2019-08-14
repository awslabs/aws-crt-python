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
#include "http_connection.h"
#include "io.h"

#include <aws/common/array_list.h>
#include <aws/http/request_response.h>
#include <aws/http/server.h>
#include <aws/io/socket.h>
#include <aws/io/stream.h>

const char *s_capsule_name_http_server = "aws_http_server";

struct py_http_server {
    struct aws_allocator *allocator;
    struct aws_http_server *server;
    PyObject *capsule;
    PyObject *on_incoming_connection;
    PyObject *on_destroy_complete;
    PyObject *bootstrap;
    bool destructor_called;
    bool destroy_called;
    bool destroy_complete;
};

static void s_http_server_destructor(PyObject *http_server_capsule) {
    struct py_http_server *py_server = PyCapsule_GetPointer(http_server_capsule, s_capsule_name_http_server);
    assert(py_server);
    py_server->destructor_called = true;
    if (py_server->server) {
        if (!py_server->destroy_called) {
            aws_http_server_release(py_server->server);
            py_server->destroy_called = true;
        }
        py_server->server = NULL;
    }
    /* the incoming callback is not freed until now */
    Py_DECREF(py_server->on_incoming_connection);

    if (py_server->destroy_complete) {
        aws_mem_release(py_server->allocator, py_server);
    }
}

static void s_on_destroy_complete(void *user_data) {
    struct py_http_server *py_server = user_data;
    
    py_server->destroy_complete = true;
    PyObject *on_destroy_complete_cb = py_server->on_destroy_complete;
    PyObject *result = NULL;
    
    if (!py_server->destructor_called) {    
        PyGILState_STATE state = PyGILState_Ensure();

        result = PyObject_CallFunction(on_destroy_complete_cb, "(N)", py_server->capsule);
        if(result){
            Py_DECREF(result);
        }
        else{
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
        Py_DECREF(on_destroy_complete_cb);
        /* Release the bootstrap until the destroy complete */
        Py_DECREF(py_server->bootstrap);
        Py_XDECREF(py_server->capsule);
        PyGILState_Release(state);
    } else if (py_server->destructor_called) {
        aws_mem_release(py_server->allocator, py_server);
    }
}

static void s_on_incoming_connection(
    struct aws_http_server *server,
    struct aws_http_connection *connection,
    int error_code,
    void *user_data) {
    (void)server;
    struct py_http_server *py_server = user_data;
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *result = NULL;
    PyObject *connection_capsule = NULL;

    PyObject *on_incoming_conn_cb = py_server->on_incoming_connection;

    struct py_http_connection *py_connection = NULL;
    py_connection = aws_mem_acquire(py_server->allocator, sizeof(struct py_http_connection));
    AWS_ZERO_STRUCT(*py_connection);
    py_connection->allocator = py_server->allocator;
    if (!error_code) {
        py_connection->connection = connection;
        connection_capsule =
            PyCapsule_New(py_connection, s_capsule_name_http_connection, s_http_connection_destructor);
        Py_XINCREF(connection_capsule);
        py_connection->capsule = connection_capsule;
        /* the callback will be fired multiple times, do not clean it up unless the server is gone */
        result = PyObject_CallFunction(on_incoming_conn_cb, "(Ni)", py_connection->capsule, error_code);
        Py_XDECREF(result);
    } else {
        aws_mem_release(py_connection->allocator, py_connection);
    }

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

    if (host_name_len >= (signed int)AWS_ADDRESS_MAX_LEN || host_name_len == 0) {
        PyErr_SetString(PyExc_ValueError, "host_name is not valid");
        goto error;
    }

    if (py_socket_options == Py_None) {
        PyErr_SetString(PyExc_ValueError, "socket_options is a required argument");
        goto error;
    }

    if (!PyCallable_Check(on_incoming_connection)) {
        PyErr_SetString(PyExc_ValueError, "on_incoming_connection callback is required");
        goto error;
    }

    if (!PyCallable_Check(on_destroy_complete)) {
        PyErr_SetString(PyExc_TypeError, "on_destroy_complete is invalid");
        goto error;
    }

    struct server_bootstrap *native_bootstrap =
        PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_server_bootstrap);
    struct aws_server_bootstrap *bootstrap = native_bootstrap->bootstrap;
    if (!bootstrap) {
        PyErr_SetString(PyExc_ValueError, "the bootstrap capsule has an invalid pointer");
        goto error;
    }

    struct aws_tls_connection_options *connection_options = NULL;

    if (tls_conn_options_capsule != Py_None) {
        connection_options = PyCapsule_GetPointer(tls_conn_options_capsule, s_capsule_name_tls_conn_options);
    }

    py_server = aws_mem_calloc(allocator, 1, sizeof(struct py_http_server));
    if (!py_server) {
        PyErr_SetAwsLastError();
        goto error;
    }

    struct aws_socket_options socket_options;
    AWS_ZERO_STRUCT(socket_options);
    if (!aws_socket_options_init_from_py(&socket_options, py_socket_options)) {
        goto error;
    }

    Py_INCREF(on_incoming_connection);
    py_server->on_incoming_connection = on_incoming_connection;

    Py_INCREF(bootstrap_capsule);
    py_server->bootstrap = bootstrap_capsule;
    
    Py_INCREF(on_destroy_complete);
    py_server->on_destroy_complete = on_destroy_complete;
    
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

    snprintf(endpoint.address, host_name_len+1, "%s", host_name);
    endpoint.port = port_number;
    options.socket_options = &socket_options;
    options.endpoint = &endpoint;
    options.on_incoming_connection = s_on_incoming_connection;
    options.on_destroy_complete = s_on_destroy_complete;
    py_server->server = aws_http_server_new(&options);
    PyObject *capsule = NULL;
    if (py_server->server) {
        /* success */
        capsule = PyCapsule_New(py_server, s_capsule_name_http_server, s_http_server_destructor);
        py_server->capsule = capsule;
    } else {
        /* fail */
        Py_DECREF(on_incoming_connection);
        Py_DECREF(on_destroy_complete);
        aws_mem_release(py_server->allocator, py_server);
    }
    Py_XINCREF(capsule);
    return capsule;
error:
    if (py_server) {
        aws_mem_release(py_server->allocator, py_server);
    }
    return NULL;
}

PyObject *aws_py_http_server_release(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *server_capsule = NULL;

    if (PyArg_ParseTuple(args, "O", &server_capsule)) {
        if (server_capsule) {
            struct py_http_server *py_server = PyCapsule_GetPointer(server_capsule, s_capsule_name_http_server);
            if (py_server->server) {
                if (!py_server->destroy_called) {
                    py_server->destroy_called = true;
                    aws_http_server_release(py_server->server);
                }
            }
        }
    }
    Py_RETURN_NONE;
}

static struct aws_http_stream *s_on_incoming_request(struct aws_http_connection *connection, void *user_data) {
    (void)connection;
    (void)user_data;
    /* fake function */
    return NULL;
}

static void s_on_shutdown(struct aws_http_connection *connection, int error_code, void *user_data) {
    (void)connection;
    struct py_http_connection *py_server_conn = user_data;
    py_server_conn->shutdown_called = true;
    PyObject *on_shutdown_cb = py_server_conn->on_connection_shutdown;

    if (!py_server_conn->destructor_called) {
        PyGILState_STATE state = PyGILState_Ensure();
        PyObject *result = PyObject_CallFunction(on_shutdown_cb, "(Ni)", py_server_conn->capsule, error_code);
        if(result){
            Py_DECREF(result);
        }
        else{
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
        Py_DECREF(py_server_conn->capsule);
        PyGILState_Release(state);
    } else {
        aws_http_connection_release(py_server_conn->connection);
        aws_mem_release(py_server_conn->allocator, py_server_conn);
    }

    Py_DECREF(on_shutdown_cb);
}

PyObject *aws_py_http_connection_configure_server(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *server_conn_capsule = NULL;
    PyObject *on_incoming_request = NULL;
    PyObject *on_shutdown = NULL;

    if (!PyArg_ParseTuple(args, "OOO", &server_conn_capsule, &on_incoming_request, &on_shutdown)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }

    struct py_http_connection *py_server_conn =
        PyCapsule_GetPointer(server_conn_capsule, s_capsule_name_http_connection);

    if (py_server_conn->on_incoming_request) {
        PyErr_SetString(PyExc_TypeError, "connection is already configured");
        goto error;
    }

    if (!on_incoming_request || !PyCallable_Check(on_incoming_request)) {
        PyErr_SetString(PyExc_TypeError, "on_incoming_request is invalid");
        goto error;
    }

    Py_INCREF(on_incoming_request);
    py_server_conn->on_incoming_request = on_incoming_request;

    if (on_shutdown) {
        if (!PyCallable_Check(on_shutdown)) {
            PyErr_SetString(PyExc_TypeError, "on_shutdown is invalid");
            goto error;
        }
        Py_INCREF(on_shutdown);
        py_server_conn->on_connection_shutdown = on_shutdown;
    }

    struct aws_http_server_connection_options options;
    AWS_ZERO_STRUCT(options);
    options.self_size = sizeof(options);
    options.connection_user_data = py_server_conn;
    options.on_incoming_request = s_on_incoming_request;
    options.on_shutdown = s_on_shutdown;

    if (aws_http_connection_configure_server(py_server_conn->connection, &options)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    Py_RETURN_NONE;

error:
    if(on_incoming_request){
        Py_DECREF(on_incoming_request);
    }
    if(on_shutdown){
        Py_DECREF(on_shutdown);
    }
    Py_RETURN_NONE;
}
