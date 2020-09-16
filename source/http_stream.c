/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "http.h"

#include <aws/http/request_response.h>

static const char *s_capsule_name_http_stream = "aws_http_stream";

/* Amount of space to reserve ahead of time for buffering headers.
 * http://dev.chromium.org/spdy/spdy-whitepaper - "typical header sizes of 700-800 bytes is common" */
#define HEADERS_RESERVED_BYTES 1024

struct http_stream_binding {
    struct aws_http_stream *native;

    /* Weak reference proxy to python self.
     * NOTE: The python self is forced to stay alive until on_complete fires.
     * We do this by INCREFing when activate() is called, and DECREFing when on_complete fires. */
    PyObject *self_proxy;

    /* Buffer up headers as they come in via repeated on_headers callacks.
     * Then deliver them to python all at once from the header_block_done callback.
     * Buffer contains null-terminated name,value pairs, for ex:
     * b'Content-Length\x00123\x00Host\x00example.com\x00' */
    struct aws_byte_buf received_headers;
    size_t received_headers_count; /* Buffer contains 2x strings per header */

    /* Dependencies that must outlive this */
    PyObject *connection;
};

struct aws_http_stream *aws_py_get_http_stream(PyObject *stream) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(stream, s_capsule_name_http_stream, "HttpStreamBase", http_stream_binding);
}

static int s_on_incoming_headers(
    struct aws_http_stream *native_stream,
    enum aws_http_header_block header_block,
    const struct aws_http_header *header_array,
    size_t num_headers,
    void *user_data) {

    (void)native_stream;
    (void)header_block;
    struct http_stream_binding *stream = user_data;
    int aws_result = AWS_OP_SUCCESS;

    /* Buffer up null-terminated strings as headers come in via repeated on_headers callacks. */
    const uint8_t terminator_byte[] = {0};
    const struct aws_byte_cursor terminator = aws_byte_cursor_from_array(terminator_byte, 1);
    for (size_t i = 0; i < num_headers; ++i) {
        const struct aws_http_header *header = &header_array[i];

        if (aws_byte_buf_append_dynamic(&stream->received_headers, &header->name) ||
            aws_byte_buf_append_dynamic(&stream->received_headers, &terminator) ||
            aws_byte_buf_append_dynamic(&stream->received_headers, &header->value) ||
            aws_byte_buf_append_dynamic(&stream->received_headers, &terminator)) {
            return AWS_OP_ERR;
        }

        stream->received_headers_count += 1;
    }

    return aws_result;
}

static int s_on_incoming_header_block_done(
    struct aws_http_stream *native_stream,
    enum aws_http_header_block header_block,
    void *user_data) {
    struct http_stream_binding *stream = user_data;

    int response_code = 0;
    if (aws_http_stream_get_incoming_response_status(native_stream, &response_code)) {
        return AWS_OP_ERR;
    }

    if (stream->received_headers_count > PY_SSIZE_T_MAX) {
        return aws_raise_error(AWS_ERROR_OVERFLOW_DETECTED);
    }
    Py_ssize_t num_headers = (Py_ssize_t)stream->received_headers_count;

    int aws_result = AWS_OP_SUCCESS;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Build up a list of (name,value) tuples,
     * extracting values from buffer of [name,value,name,value,...] null-terminated strings */
    PyObject *header_list = PyList_New(num_headers);
    if (!header_list) {
        aws_result = aws_py_raise_error();
        goto done;
    }

    struct aws_byte_cursor string_cursor = aws_byte_cursor_from_buf(&stream->received_headers);

    for (Py_ssize_t i = 0; i < num_headers; ++i) {
        const char *name_str = (const char *)string_cursor.ptr;
        size_t name_len = strlen((const char *)string_cursor.ptr);

        aws_byte_cursor_advance(&string_cursor, name_len + 1);

        const char *value_str = (const char *)string_cursor.ptr;
        size_t value_len = strlen((const char *)string_cursor.ptr);

        aws_byte_cursor_advance(&string_cursor, value_len + 1);

        PyObject *tuple = Py_BuildValue("(s#s#)", name_str, name_len, value_str, value_len);
        if (!tuple) {
            aws_result = aws_py_raise_error();
            goto done;
        }

        PyList_SET_ITEM(header_list, i, tuple); /* steals reference to tuple */
    }

    /* TODO: handle informational and trailing headers */
    if (header_block == AWS_HTTP_HEADER_BLOCK_MAIN) {

        /* Deliver the built up list of (name,value) tuples */
        PyObject *result = PyObject_CallMethod(stream->self_proxy, "_on_response", "(iO)", response_code, header_list);
        if (!result) {
            aws_result = aws_py_raise_error();
            goto done;
        }
        Py_DECREF(result);
    }

    /* Clear the buffer so we're ready for next header block */
    stream->received_headers.len = 0;
    stream->received_headers_count = 0;

done:
    Py_XDECREF(header_list);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return aws_result;
}

static int s_on_incoming_body(
    struct aws_http_stream *native_stream,
    const struct aws_byte_cursor *data,
    void *user_data) {

    (void)native_stream;

    struct http_stream_binding *stream = user_data;

    if (data->len > PY_SSIZE_T_MAX) {
        return aws_raise_error(AWS_ERROR_OVERFLOW_DETECTED);
    }
    Py_ssize_t data_len = (Py_ssize_t)data->len;

    int aws_result = AWS_OP_SUCCESS;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(stream->self_proxy, "_on_body", "(y#)", (const char *)data->ptr, data_len);
    if (!result) {
        aws_result = aws_py_raise_error();
        goto done;
    }
    Py_DECREF(result);

done:
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return aws_result;
}

static void s_on_stream_complete(struct aws_http_stream *native_stream, int error_code, void *user_data) {
    (void)native_stream;
    struct http_stream_binding *stream = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(stream->self_proxy, "_on_complete", "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    /* DECREF python self, we don't need to force it to stay alive any longer. */
    Py_DECREF(PyWeakref_GetObject(stream->self_proxy));

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

static void s_stream_capsule_destructor(PyObject *http_stream_capsule) {
    struct http_stream_binding *stream = PyCapsule_GetPointer(http_stream_capsule, s_capsule_name_http_stream);

    /* Destructor runs under 2 possible conditions:
     * 1) Creation failed, so every possible resource might need to be cleaned up.
     * 2) Stream successfully reached end of life, and on_complete has already fired. */

    aws_http_stream_release(stream->native);
    Py_XDECREF(stream->self_proxy);
    aws_byte_buf_clean_up(&stream->received_headers);
    Py_XDECREF(stream->connection);

    aws_mem_release(aws_py_get_allocator(), stream);
}

PyObject *aws_py_http_client_stream_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *py_stream = NULL;
    PyObject *py_connection = NULL;
    PyObject *py_request = NULL;
    if (!PyArg_ParseTuple(args, "OOO", &py_stream, &py_connection, &py_request)) {
        return NULL;
    }

    struct aws_http_connection *native_connection = aws_py_get_http_connection(py_connection);
    if (!native_connection) {
        return NULL;
    }

    struct aws_http_message *native_request = aws_py_get_http_message(py_request);
    if (!native_request) {
        return NULL;
    }

    struct http_stream_binding *stream = aws_mem_calloc(allocator, 1, sizeof(struct http_stream_binding));
    if (!stream) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside http_stream_binding */

    PyObject *capsule = PyCapsule_New(stream, s_capsule_name_http_stream, s_stream_capsule_destructor);
    if (!capsule) {
        goto error;
    }

    stream->connection = py_connection;
    Py_INCREF(stream->connection);

    stream->self_proxy = PyWeakref_NewProxy(py_stream, NULL);
    if (!stream->self_proxy) {
        goto error;
    }

    if (aws_byte_buf_init(&stream->received_headers, allocator, HEADERS_RESERVED_BYTES)) {
        goto error;
    }

    struct aws_http_make_request_options request_options = {
        .self_size = sizeof(request_options),
        .request = native_request,
        .on_response_headers = s_on_incoming_headers,
        .on_response_header_block_done = s_on_incoming_header_block_done,
        .on_response_body = s_on_incoming_body,
        .on_complete = s_on_stream_complete,
        .user_data = stream,
    };

    stream->native = aws_http_connection_make_request(native_connection, &request_options);
    if (!stream->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;

error:
    if (capsule) {
        Py_DECREF(capsule);
    } else {
        aws_mem_release(allocator, stream);
    }
    return NULL;
}

PyObject *aws_py_http_client_stream_activate(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_stream = NULL;
    if (!PyArg_ParseTuple(args, "O", &py_stream)) {
        return NULL;
    }

    struct aws_http_stream *native_stream = aws_py_get_http_stream(py_stream);
    if (!native_stream) {
        return NULL;
    }

    if (aws_http_stream_activate(native_stream)) {
        return PyErr_AwsLastError();
    }

    /* Force python self to stay alive until on_complete callback */
    Py_INCREF(py_stream);

    Py_RETURN_NONE;
}
