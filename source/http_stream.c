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
#include "http_stream.h"

#include "http_connection.h"
#include <aws/http/connection.h>
#include <aws/http/request_response.h>

static const char *s_capsule_name_http_stream = "aws_http_stream";

struct http_stream_binding {
    struct aws_http_stream *native;

    /* These references will be cleared after on_complete has fired */
    PyObject *self; /* Keep python self alive until on_complete */
    PyObject *on_stream_completed;
    PyObject *on_incoming_headers_received;
    PyObject *on_read_body;
    PyObject *on_incoming_body;
    PyObject *received_headers;

    /* Dependencies that must outlive this */
    PyObject *connection;
};

struct aws_http_stream *aws_py_get_http_stream(PyObject *stream) {
    struct aws_http_stream *native = NULL;

    PyObject *capsule = PyObject_GetAttrString(stream, "_binding");
    if (capsule) {
        struct http_stream_binding *binding = PyCapsule_GetPointer(capsule, s_capsule_name_http_stream);
        if (binding) {
            native = binding->native;
            AWS_FATAL_ASSERT(native);
        }
        Py_DECREF(capsule);
    }

    return native;
}

static enum aws_http_outgoing_body_state s_stream_outgoing_body(
    struct aws_http_stream *internal_stream,
    struct aws_byte_buf *buf,
    void *user_data) {
    (void)internal_stream;

    struct http_stream_binding *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *mv = aws_py_memory_view_from_byte_buffer(buf, PyBUF_WRITE);

    if (!mv) {
        aws_http_connection_close(aws_http_stream_get_connection(stream->native));
        PyGILState_Release(state);
        return AWS_HTTP_OUTGOING_BODY_DONE;
    }

    PyObject *result = PyObject_CallFunction(stream->on_read_body, "(O)", mv);
    /* the return from python land is a tuple where the first argument is the body state
     * and the second is the amount written */
    PyObject *state_code = PyTuple_GetItem(result, 0);
    enum aws_http_outgoing_body_state body_state = (enum aws_http_outgoing_body_state)PyIntEnum_AsLong(state_code);
    PyObject *written_obj = PyTuple_GetItem(result, 1);
    long written = (long)PyLong_AsLong(written_obj);
    Py_XDECREF(result);
    Py_XDECREF(mv);

    PyGILState_Release(state);

    buf->len += written;

    return body_state;
}

static void s_on_incoming_response_headers(
    struct aws_http_stream *internal_stream,
    const struct aws_http_header *header_array,
    size_t num_headers,
    void *user_data) {
    (void)internal_stream;
    struct http_stream_binding *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();

    for (size_t i = 0; i < num_headers; ++i) {
        PyObject *key = PyString_FromStringAndSize((const char *)header_array[i].name.ptr, header_array[i].name.len);
        PyObject *value =
            PyString_FromStringAndSize((const char *)header_array[i].value.ptr, header_array[i].value.len);

        PyDict_SetItem(stream->received_headers, key, value);
    }
    PyGILState_Release(state);
}

static void s_on_incoming_header_block_done(struct aws_http_stream *internal_stream, bool has_body, void *user_data) {

    struct http_stream_binding *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();
    int response_code = 0;
    aws_http_stream_get_incoming_response_status(internal_stream, &response_code);

    PyObject *has_body_obj = has_body ? Py_True : Py_False;

    PyObject *result = PyObject_CallFunction(
        stream->on_incoming_headers_received, "(OiO)", stream->received_headers, response_code, has_body_obj);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_XDECREF(result);
    Py_CLEAR(stream->received_headers);
    Py_CLEAR(stream->on_incoming_headers_received);
    PyGILState_Release(state);
}

static void s_on_incoming_response_body(
    struct aws_http_stream *internal_stream,
    const struct aws_byte_cursor *data,
    size_t *out_window_update_size,
    void *user_data) {
    (void)internal_stream;
    (void)out_window_update_size;

    struct http_stream_binding *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();

    Py_ssize_t data_len = (Py_ssize_t)data->len;
    PyObject *result =
        PyObject_CallFunction(stream->on_incoming_body, "(" BYTE_BUF_FORMAT_STR ")", (const char *)data->ptr, data_len);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_XDECREF(result);
    PyGILState_Release(state);
}

static void s_on_stream_complete(struct aws_http_stream *internal_stream, int error_code, void *user_data) {
    (void)internal_stream;
    struct http_stream_binding *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(stream->on_stream_completed, "(i)", error_code);
    if (!result) {
        /* This function must succeed. Can't leave a Future incomplete. */
        PyErr_WriteUnraisable(PyErr_Occurred());
        AWS_FATAL_ASSERT(0);
    }
    Py_DECREF(result);

    /* There will be no more callbacks, clear */
    Py_CLEAR(stream->on_stream_completed);
    Py_CLEAR(stream->on_incoming_headers_received);
    Py_CLEAR(stream->on_read_body);
    Py_CLEAR(stream->on_incoming_body);
    Py_CLEAR(stream->received_headers);
    Py_CLEAR(stream->self);

    PyGILState_Release(state);
}

static void s_stream_capsule_destructor(PyObject *http_stream_capsule) {
    struct http_stream_binding *stream = PyCapsule_GetPointer(http_stream_capsule, s_capsule_name_http_stream);

    /* If native stream was created, on_complete was already called and most references have already been cleared.
     * Otherwise, native stream failed creation, so we need to clear everything */
    if (stream->native) {
        AWS_FATAL_ASSERT(stream->on_stream_completed == NULL);

        aws_http_stream_release(stream->native);
    } else {
        Py_DECREF(stream->on_stream_completed);
        Py_DECREF(stream->on_incoming_headers_received);
        Py_DECREF(stream->on_read_body);
        Py_DECREF(stream->on_incoming_body);
        Py_DECREF(stream->received_headers);
        Py_DECREF(stream->self);
    }

    Py_DECREF(stream->connection);
    aws_mem_release(aws_py_get_allocator(), stream);
}

PyObject *aws_py_http_client_stream_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct http_stream_binding *stream = aws_mem_calloc(allocator, 1, sizeof(struct http_stream_binding));
    if (!stream) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    PyObject *py_connection = NULL;
    PyObject *py_http_request = NULL;
    PyObject *on_stream_completed = NULL;
    PyObject *on_incoming_headers_received = NULL;
    if (!PyArg_ParseTuple(
            args, "OOOO", &py_connection, &py_http_request, &on_stream_completed, &on_incoming_headers_received)) {
        PyErr_SetNone(PyExc_ValueError);
        goto clean_up_stream;
    }

    struct aws_http_connection *native_connection = aws_py_get_http_connection(py_connection);
    if (!native_connection) {
        goto clean_up_stream;
    }

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

    stream->self = py_http_request;
    Py_XINCREF(stream->self);
    stream->connection = py_connection;
    Py_XINCREF(stream->connection);
    stream->on_stream_completed = on_stream_completed;
    Py_XINCREF(on_stream_completed);
    stream->on_incoming_headers_received = on_incoming_headers_received;
    Py_XINCREF(on_incoming_headers_received);

    struct aws_http_request_options request_options = {
        .self_size = sizeof(request_options),
        .client_connection = native_connection,
    };

    PyObject *method_str = PyObject_GetAttrString(py_http_request, "method");
    if (!method_str) {
        PyErr_SetString(PyExc_ValueError, "http method is required");
        goto clean_up_stream;
    }

    request_options.method = aws_byte_cursor_from_pystring(method_str);

    PyObject *uri_str = PyObject_GetAttrString(py_http_request, "path_and_query");
    if (!uri_str) {
        PyErr_SetString(PyExc_ValueError, "The URI path and query is required");
        goto clean_up_stream;
    }

    request_options.uri = aws_byte_cursor_from_pystring(uri_str);

    PyObject *request_headers = PyObject_GetAttrString(py_http_request, "outgoing_headers");
    if (!request_headers) {
        PyErr_SetString(PyExc_ValueError, "outgoing headers is required");
        goto clean_up_stream;
    }

    Py_ssize_t num_headers = PyDict_Size(request_headers);
    struct aws_array_list headers;

    if (num_headers > 0) {
        if (aws_array_list_init_dynamic(&headers, allocator, (size_t)num_headers, sizeof(struct aws_http_header))) {
            PyErr_SetAwsLastError();
            goto clean_up_headers;
        }

        PyObject *key, *value;
        Py_ssize_t pos = 0;

        while (PyDict_Next(request_headers, &pos, &key, &value)) {
            struct aws_http_header http_header;
            http_header.name = aws_byte_cursor_from_pystring(key);
            http_header.value = aws_byte_cursor_from_pystring(value);

            aws_array_list_push_back(&headers, &http_header);
        }

        request_options.header_array = headers.data;
        request_options.num_headers = (size_t)num_headers;
    }

    PyObject *on_read_body = PyObject_GetAttrString(py_http_request, "_on_read_body");
    if (on_read_body && on_read_body != Py_None) {
        stream->on_read_body = on_read_body;
        Py_XINCREF(on_read_body);
        request_options.stream_outgoing_body = s_stream_outgoing_body;
    }

    PyObject *on_incoming_body = PyObject_GetAttrString(py_http_request, "_on_incoming_body");
    if (on_incoming_body && on_incoming_body != Py_None) {
        stream->on_incoming_body = on_incoming_body;
        Py_XINCREF(on_incoming_body);
        request_options.on_response_body = s_on_incoming_response_body;
    }

    stream->received_headers = PyDict_New();
    request_options.on_response_headers = s_on_incoming_response_headers;
    request_options.on_response_header_block_done = s_on_incoming_header_block_done;
    request_options.on_complete = s_on_stream_complete;
    request_options.user_data = stream;

    struct aws_http_stream *http_stream = aws_http_stream_new_client_request(&request_options);
    aws_array_list_clean_up(&headers);

    if (!http_stream) {
        goto clean_up_headers;
    }

    stream->native = http_stream;
    return PyCapsule_New(stream, s_capsule_name_http_stream, s_stream_capsule_destructor);

clean_up_headers:
    aws_array_list_clean_up(&headers);

clean_up_stream:
    aws_mem_release(allocator, stream);

    return NULL;
}
