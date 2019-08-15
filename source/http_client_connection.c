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
#include "http_stream.h"
#include "http_connection.h"
#include "io.h"

#include <aws/common/array_list.h>
#include <aws/io/socket.h>
#include <aws/io/stream.h>
#include <aws/http/request_response.h>


static void s_on_client_connection_setup(struct aws_http_connection *connection, int error_code, void *user_data) {

    struct py_http_connection *py_client_connection = user_data;
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *result = NULL;
    PyObject *capsule = NULL;

    PyObject *on_conn_setup_cb = py_client_connection->on_connection_setup;

    if (!error_code) {
        py_client_connection->connection = connection;
        capsule =
            PyCapsule_New(py_client_connection, s_capsule_name_http_connection, s_http_connection_destructor);
        py_client_connection->capsule = capsule;
    } else {
        aws_mem_release(py_client_connection->allocator, py_client_connection);
    }

    result = PyObject_CallFunction(on_conn_setup_cb, "(Ni)", capsule, error_code);

    Py_DECREF(on_conn_setup_cb);
    Py_XDECREF(result);

    PyGILState_Release(state);
}

static void s_on_client_connection_shutdown(struct aws_http_connection *connection, int error_code, void *user_data) {
    (void)connection;
    struct py_http_connection *py_client_connection = user_data;
    py_client_connection->shutdown_called = true;
    PyObject *on_conn_shutdown_cb = py_client_connection->on_connection_shutdown;

    if (!py_client_connection->destructor_called && on_conn_shutdown_cb) {
        PyGILState_STATE state = PyGILState_Ensure();
        PyObject *result = PyObject_CallFunction(on_conn_shutdown_cb, "(i)", error_code);
        Py_XDECREF(result);
        PyGILState_Release(state);
    } else if (py_client_connection->destructor_called) {
        aws_http_connection_release(py_client_connection->connection);
        aws_mem_release(py_client_connection->allocator, py_client_connection);
    }

    Py_XDECREF(on_conn_shutdown_cb);
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

    if (!PyArg_ParseTuple(
            args,
            "OOOs#HOO",
            &bootstrap_capsule,
            &on_connection_setup,
            &on_connection_shutdown,
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

    if (!on_connection_setup || on_connection_setup == Py_None) {
        PyErr_SetString(PyExc_ValueError, "on_connection_setup callback is required");
        goto error;
    }

    struct client_bootstrap *native_bootstrap = PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_client_bootstrap);
    struct aws_client_bootstrap *bootstrap = native_bootstrap->bootstrap;
    if (!bootstrap) {
        PyErr_SetString(PyExc_ValueError, "the bootstrap capsule has an invalid pointer");
        goto error;
    }

    struct aws_tls_connection_options *connection_options = NULL;

    if (tls_conn_options_capsule != Py_None) {
        connection_options = PyCapsule_GetPointer(tls_conn_options_capsule, s_capsule_name_tls_conn_options);
    }

    py_connection = aws_mem_acquire(allocator, sizeof(struct py_http_connection));
    if (!py_connection) {
        PyErr_SetAwsLastError();
        goto error;
    }
    AWS_ZERO_STRUCT(*py_connection);

    py_connection->bootstrap = bootstrap_capsule;
    Py_INCREF(bootstrap_capsule);

    struct aws_socket_options socket_options;
    
    if(!aws_socket_options_init_from_py(&socket_options, py_socket_options)){
        goto error;
    }

    if (!PyCallable_Check(on_connection_setup)) {
        PyErr_SetString(PyExc_TypeError, "on_connection_setup is invalid");
        goto error;
    }

    Py_XINCREF(on_connection_setup);
    py_connection->on_connection_setup = on_connection_setup;

    py_connection->on_connection_shutdown = NULL;
    if (on_connection_shutdown && on_connection_shutdown != Py_None) {
        if (!PyCallable_Check(on_connection_shutdown)) {
            PyErr_SetString(PyExc_TypeError, "on_connection_shutdown is invalid");
            goto error;
        }
        Py_XINCREF(on_connection_shutdown);
        py_connection->on_connection_shutdown = on_connection_shutdown;
    }

    py_connection->allocator = allocator;

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

static int s_stream_read(struct aws_input_stream *stream, struct aws_byte_buf *dest) {
    struct py_http_stream *py_stream = stream->impl;

    int err = AWS_OP_SUCCESS;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *mv = aws_py_memory_view_from_byte_buffer(dest, PyBUF_WRITE);

    if (!mv) {
        PyGILState_Release(state);
        return AWS_OP_ERR;
    }

    PyObject *readinto = PyObject_GetAttrString(py_stream->outgoing_body, "readinto");
    AWS_ASSERT(readinto);

    PyObject *result = PyObject_CallFunction(readinto, "(O)", mv);

    if (result && result != Py_None) {
        if (!PyLong_Check(result)) {
            /* Log that readinto must throw BlockingIOError, return None, or a number, and return error */
            err = AWS_OP_ERR;
        }
        /* Number returned, successful read */
        size_t amount_read = PyLong_AsSize_t(result);
        Py_DECREF(result);

        /* Returning 0 means we're at the end of the stream. */
        if (amount_read == 0) {
            py_stream->is_eos = true;
        } else {
            dest->len += amount_read;
        }
    } else {
        /* No result or not a number, clear the exception flag (BufferedIOBase throws BlockingIOError if data is
        unavailable), and return that 0 data was read. Try again later. */
        PyErr_Clear();
    }
    /* DECREF this twice? */
    //Py_XDECREF(result);
    Py_DECREF(mv);

    PyGILState_Release(state);

    return err;
}

static int s_stream_get_status(struct aws_input_stream *stream, struct aws_stream_status *status) {
    struct py_http_stream *py_stream = stream->impl;

    status->is_valid = true;
    status->is_end_of_stream = py_stream->is_eos;

    return AWS_OP_SUCCESS;
}

struct aws_input_stream_vtable s_py_stream_vtable = {
    .seek = NULL,
    .read = s_stream_read,
    .get_status = s_stream_get_status,
    .get_length = NULL,
    .clean_up = NULL,
};


static int s_on_incoming_header_block_done(struct aws_http_stream *internal_stream, bool has_body, void *user_data) {

    struct py_http_stream *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();
    int response_code = 0;
    aws_http_stream_get_incoming_response_status(internal_stream, &response_code);

    PyObject *has_body_obj = has_body ? Py_True : Py_False;

    PyObject *result = PyObject_CallFunction(
        stream->on_incoming_headers_received, "(OiO)", stream->received_headers, response_code, has_body_obj);
    Py_XDECREF(result);
    Py_XDECREF(stream->received_headers);
    Py_DECREF(stream->on_incoming_headers_received);
    PyGILState_Release(state);

    return AWS_OP_SUCCESS;
}

PyObject *aws_py_http_client_connection_make_request(PyObject *self, PyObject *args) {
    (void)self;

    struct py_http_connection *py_connection = NULL;
    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    struct py_http_stream *stream = aws_mem_acquire(allocator, sizeof(struct py_http_stream));
    if (!stream) {
        PyErr_SetAwsLastError();
        return NULL;
    }
    struct aws_http_message *request = aws_http_message_new_request(allocator);
    if (!request) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    AWS_ZERO_STRUCT(*stream);
    stream->allocator = allocator;
    stream->body_input_stream.allocator = allocator;
    stream->body_input_stream.vtable = &s_py_stream_vtable;
    stream->body_input_stream.impl = stream;

    PyObject *http_connection_capsule = NULL;
    PyObject *py_http_request = NULL;
    PyObject *on_stream_completed = NULL;
    PyObject *on_incoming_headers_received = NULL;

    if (!PyArg_ParseTuple(
            args,
            "OOOO",
            &http_connection_capsule,
            &py_http_request,
            &on_stream_completed,
            &on_incoming_headers_received)) {
        PyErr_SetNone(PyExc_ValueError);
        goto clean_up_stream;
    }

    if (!http_connection_capsule || !PyCapsule_CheckExact(http_connection_capsule)) {
        PyErr_SetString(PyExc_ValueError, "http connection capsule is invalid");
        goto clean_up_stream;
    }

    py_connection = PyCapsule_GetPointer(http_connection_capsule, s_capsule_name_http_connection);
    stream->connection_capsule = http_connection_capsule;

    if (!py_http_request) {
        PyErr_SetString(PyExc_ValueError, "the request argument is required");
        goto clean_up_stream;
    }

    if (!on_stream_completed) {
        PyErr_SetString(PyExc_ValueError, "on_stream_completed callback is required");
        goto clean_up_stream;
    }

    if (!on_incoming_headers_received) {
        PyErr_SetString(PyExc_ValueError, "on_incoming_headers_received callback is required");
        goto clean_up_stream;
    }

    stream->on_stream_completed = on_stream_completed;
    Py_XINCREF(on_stream_completed);
    stream->on_incoming_headers_received = on_incoming_headers_received;
    Py_XINCREF(on_incoming_headers_received);

    struct aws_http_request_options request_options;
    AWS_ZERO_STRUCT(request_options);
    request_options.self_size = sizeof(request_options);
    request_options.client_connection = py_connection->connection;
    request_options.request = request;

    PyObject *method_str = PyObject_GetAttrString(py_http_request, "method");
    if (!method_str) {
        PyErr_SetString(PyExc_ValueError, "http method is required");
        goto clean_up_stream;
    }
    aws_http_message_set_request_method(request, aws_byte_cursor_from_pystring(method_str));

    PyObject *uri_str = PyObject_GetAttrString(py_http_request, "path_and_query");
    if (!uri_str) {
        PyErr_SetString(PyExc_ValueError, "The URI path and query is required");
        goto clean_up_stream;
    }
    aws_http_message_set_request_path(request, aws_byte_cursor_from_pystring(uri_str));

    PyObject *request_headers = PyObject_GetAttrString(py_http_request, "outgoing_headers");
    if (!request_headers) {
        PyErr_SetString(PyExc_ValueError, "outgoing headers is required");
        goto clean_up_stream;
    }

    Py_ssize_t num_headers = PyDict_Size(request_headers);
    if (num_headers > 0) {
        PyObject *key, *value;
        Py_ssize_t pos = 0;

        while (PyDict_Next(request_headers, &pos, &key, &value)) {
            struct aws_http_header http_header;
            http_header.name = aws_byte_cursor_from_pystring(key);
            http_header.value = aws_byte_cursor_from_pystring(value);

            aws_http_message_add_header(request, http_header);
        }
    }

    PyObject *outgoing_body = PyObject_GetAttrString(py_http_request, "_outgoing_body");
    if (outgoing_body && outgoing_body != Py_None) {
        /* Check that the stream has a readinto method */
        PyObject *readinto = PyObject_GetAttrString(outgoing_body, "readinto");
        if (readinto && readinto != Py_None) {
            stream->outgoing_body = outgoing_body;
            Py_INCREF(outgoing_body);
            aws_http_message_set_body_stream(request, &stream->body_input_stream);
        }
    }

    PyObject *on_incoming_body = PyObject_GetAttrString(py_http_request, "_on_incoming_body");
    if (on_incoming_body && on_incoming_body != Py_None) {
        stream->on_incoming_body = on_incoming_body;
        Py_XINCREF(on_incoming_body);
        request_options.on_response_body = native_on_incoming_body;
    }

    stream->received_headers = PyDict_New();
    request_options.on_response_headers = native_on_incoming_headers;
    request_options.on_response_header_block_done = s_on_incoming_header_block_done;
    request_options.on_complete = native_on_stream_complete;
    request_options.user_data = stream;

    struct aws_http_stream *http_stream = aws_http_stream_new_client_request(&request_options);
    if (!http_stream) {
        goto clean_up_stream;
    }

    stream->stream = http_stream;
    Py_INCREF(stream->connection_capsule);
    return PyCapsule_New(stream, s_capsule_name_http_stream, native_http_stream_destructor);

clean_up_stream:
    aws_http_message_destroy(request);
    aws_mem_release(allocator, stream);

    return NULL;
}
