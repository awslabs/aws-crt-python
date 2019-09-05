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

#include <aws/http/request_response.h>

static const char *s_capsule_name_http_stream = "aws_http_stream";

struct http_stream_binding {
    struct aws_http_stream *native;

    /* Weak reference proxy to python self.
     * NOTE: The python self is forced to stay alive until on_complete fires.
     * We do this by INCREFing when setup is successful, and DECREFing when on_complete fires. */
    PyObject *self_proxy;

    /* Build up list of (name,value) tuples as headers come in via repeated on_headers callacks.
     * Then deliver them to python all at once from the header_block_done callback */
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

static int s_on_incoming_headers(
    struct aws_http_stream *native_stream,
    const struct aws_http_header *header_array,
    size_t num_headers,
    void *user_data) {

    struct http_stream_binding *stream = user_data;
    int aws_result = AWS_OP_SUCCESS;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    /* Set this just in case callback fires before aws_http_connection_make_request() has even returned */
    stream->native = native_stream;

    /* Build up list of (name,value) tuples as headers come in via repeated on_headers callacks. */
    for (size_t i = 0; i < num_headers; ++i) {
        const struct aws_http_header *header = &header_array[i];

        PyObject *name_value_pair = Py_BuildValue(
            "(s#s#)",
            (const char *)header->name.ptr,
            header->name.len,
            (const char *)header->value.ptr,
            header->value.len);
        if (!name_value_pair) {
            aws_result = aws_raise_py_error();
            goto done;
        }

        bool append_success = PyList_Append(stream->received_headers, name_value_pair) == 0;
        Py_DECREF(name_value_pair);
        if (!append_success) {
            aws_result = aws_raise_py_error();
            goto done;
        }
    }

done:
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return aws_result;
}

static int s_on_incoming_header_block_done(struct aws_http_stream *native_stream, bool has_body, void *user_data) {
    (void)has_body;
    struct http_stream_binding *stream = user_data;

    int response_code = 0;
    if (aws_http_stream_get_incoming_response_status(native_stream, &response_code)) {
        return AWS_OP_ERR;
    }

    int aws_result = AWS_OP_SUCCESS;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    /* Set this just in case callback fires before aws_http_connection_make_request() has even returned */
    stream->native = native_stream;

    /* Deliver the built up list of (name,value) tuples */
    PyObject *result =
        PyObject_CallMethod(stream->self_proxy, "_on_response", "(iO)", response_code, stream->received_headers);
    if (!result) {
        aws_result = aws_raise_py_error();
        goto done;
    }
    Py_DECREF(result);

    /* Clear the list so we're ready for next header block */
    result = PyObject_CallMethod(stream->received_headers, "clear", "()", NULL);
    if (!result) {
        aws_result = aws_raise_py_error();
        goto done;
    }
    Py_DECREF(result);

done:
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
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallMethod(
        stream->self_proxy, "_on_body", "(" READABLE_BYTES_FORMAT_STR ")", (const char *)data->ptr, data_len);
    if (!result) {
        aws_result = aws_raise_py_error();
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
    PyGILState_STATE state = PyGILState_Ensure();

    /* Set this just in case callback fires before aws_http_connection_make_request() has even returned */
    stream->native = native_stream;

    PyObject *result = PyObject_CallMethod(stream->self_proxy, "_on_complete", "(i)", error_code);
    if (!result) {
        /* This function must succeed. Can't leave a Future incomplete. */
        PyErr_WriteUnraisable(PyErr_Occurred());
        AWS_FATAL_ASSERT(0);
    }
    Py_DECREF(result);

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
    Py_XDECREF(stream->received_headers);
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

    stream->received_headers = PyList_New(0);
    if (!stream->received_headers) {
        goto error;
    }

    /* NOTE: Callbacks might start firing before aws_http_connection_make_request() can even return.
     * Therefore, we set `HttpClientStream._binding = capsule` now, instead of returning capsule to caller */
    if (PyObject_SetAttrString(py_stream, "_binding", capsule) == -1) {
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

    /* From hereon, nothing will fail */

    /* Force python self to stay alive until on_complete callback */
    Py_INCREF(py_stream);

    Py_DECREF(capsule);
    Py_RETURN_NONE;

error:
    if (capsule) {
        Py_DECREF(capsule);
    } else {
        aws_mem_release(allocator, stream);
    }
    return NULL;
}
