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

#include "io.h"

#include <aws/common/array_list.h>
#include <aws/io/socket.h>
#include <aws/io/stream.h>

const char *s_capsule_name_http_stream = "aws_http_client_stream";


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

int native_on_incoming_headers(
    struct aws_http_stream *internal_stream,
    const struct aws_http_header *header_array,
    size_t num_headers,
    void *user_data) {
    (void)internal_stream;
    struct py_http_stream *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();

    for (size_t i = 0; i < num_headers; ++i) {
        PyObject *key = PyString_FromStringAndSize((const char *)header_array[i].name.ptr, header_array[i].name.len);
        PyObject *value =
            PyString_FromStringAndSize((const char *)header_array[i].value.ptr, header_array[i].value.len);

        PyDict_SetItem(stream->received_headers, key, value);
    }
    PyGILState_Release(state);

    return AWS_OP_SUCCESS;
}

int native_on_incoming_body(
    struct aws_http_stream *internal_stream,
    const struct aws_byte_cursor *data,
    void *user_data) {
    (void)internal_stream;

    int err = AWS_OP_SUCCESS;

    struct py_http_stream *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();

    Py_ssize_t data_len = (Py_ssize_t)data->len;
    PyObject *result =
        PyObject_CallFunction(stream->on_incoming_body, "(" BYTE_BUF_FORMAT_STR ")", (const char *)data->ptr, data_len);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        err = AWS_OP_ERR;
    }
    Py_XDECREF(result);
    PyGILState_Release(state);

    return err;
}

void native_on_stream_complete(struct aws_http_stream *internal_stream, int error_code, void *user_data) {
    (void)internal_stream;
    struct py_http_stream *stream = user_data;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(stream->on_stream_completed, "(i)", error_code);
    Py_XDECREF(result);
    Py_XDECREF(stream->on_stream_completed);
    Py_XDECREF(stream->on_incoming_body);
    Py_XDECREF(stream->outgoing_body);

    PyGILState_Release(state);
}

void native_http_stream_destructor(PyObject *http_stream_capsule) {
    struct py_http_stream *stream = PyCapsule_GetPointer(http_stream_capsule, s_capsule_name_http_stream);
    assert(stream);

    aws_http_stream_release(stream->stream);
    Py_DECREF(stream->connection_capsule);
    aws_mem_release(stream->allocator, stream);
}
