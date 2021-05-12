/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "event_stream.h"

#include <aws/event-stream/event_stream_rpc_client.h>

struct continuation_binding;
static void s_continuation_capsule_destructor(PyObject *capsule);
static void s_on_continuation_closed(struct aws_event_stream_rpc_client_continuation_token *native, void *user_data);
static void s_on_continuation_message(
    struct aws_event_stream_rpc_client_continuation_token *native,
    const struct aws_event_stream_rpc_message_args *message_args,
    void *user_data);

static const char *s_capsule_name = "aws_event_stream_rpc_client_continuation_token";

struct continuation_binding {
    struct aws_event_stream_rpc_client_continuation_token *native;
    struct aws_event_stream_rpc_client_connection *native_connection;

    /* This reference is solely used for invoking callbacks,
     * It is not set until activate(), and cleared upon on_continuation_closed().
     * If it were not cleared, circular references between the python object
     * and its binding would prevent the GC from ever cleaning things up */
    PyObject *self_py;
};

struct aws_event_stream_rpc_client_continuation_token *aws_py_get_event_stream_rpc_client_continuation(
    PyObject *continuation) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(continuation, s_capsule_name, "ClientContinuation", continuation_binding);
}

PyObject *aws_py_event_stream_rpc_client_connection_new_stream(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *connection_py;
    if (!PyArg_ParseTuple(args, "O", &connection_py)) {
        return NULL;
    }

    struct aws_event_stream_rpc_client_connection *native_connection =
        aws_py_get_event_stream_rpc_client_connection(connection_py);
    if (!native_connection) {
        return NULL;
    }

    struct continuation_binding *continuation =
        aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct continuation_binding));
    continuation->native_connection = native_connection;

    PyObject *capsule = PyCapsule_New(continuation, s_capsule_name, s_continuation_capsule_destructor);
    if (!capsule) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    struct aws_event_stream_rpc_client_stream_continuation_options options = {
        .on_continuation = s_on_continuation_message,
        .on_continuation_closed = s_on_continuation_closed,
        .user_data = continuation,
    };
    continuation->native = aws_event_stream_rpc_client_connection_new_stream(native_connection, &options);
    if (!continuation->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;
error:
    /* capsule's destructor will clean up anything inside of it */
    Py_DECREF(capsule);
    return NULL;
}

static void s_on_continuation_closed(struct aws_event_stream_rpc_client_continuation_token *native, void *user_data) {
    (void)native;
    struct continuation_binding *continuation = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(continuation->self_py, "_on_continuation_closed", "()");
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(continuation->self_py);
    }

    /* There will be no further callbacks, clear circular reference
     * so that python continuation object can ever be GC'd */
    Py_CLEAR(continuation->self_py);

    PyGILState_Release(state);
}

static void s_continuation_capsule_destructor(PyObject *capsule) {
    struct continuation_binding *continuation = PyCapsule_GetPointer(capsule, s_capsule_name);
    aws_event_stream_rpc_client_continuation_release(continuation->native);
    aws_mem_release(aws_py_get_allocator(), continuation);
}

static void s_on_continuation_message(
    struct aws_event_stream_rpc_client_continuation_token *native,
    const struct aws_event_stream_rpc_message_args *message_args,
    void *user_data) {

    (void)native;
    struct continuation_binding *continuation = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *headers = NULL;
    PyObject *result = NULL;

    headers = aws_py_event_stream_python_headers_create(message_args->headers, message_args->headers_count);
    if (!headers) {
        PyErr_WriteUnraisable(continuation->self_py);
        goto done;
    }

    result = PyObject_CallMethod(
        continuation->self_py,
        "_on_continuation_message",
        "(Oy#iI)",
        headers,
        message_args->payload->buffer,
        message_args->payload->len,
        message_args->message_type,
        message_args->message_flags);
    if (!result) {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(continuation->self_py);
        goto done;
    }

done:
    Py_XDECREF(headers);
    Py_XDECREF(result);
    PyGILState_Release(state);
}

PyObject *aws_py_event_stream_rpc_client_continuation_activate(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *capsule_py;
    PyObject *self_py;
    const char *operation_name;
    Py_ssize_t operation_name_len;
    PyObject *headers_py;
    Py_buffer payload_buf; /* Py_buffers must be released after successful PyArg_ParseTuple() calls */
    int message_type;
    uint32_t message_flags;
    PyObject *on_flush_py;
    if (!PyArg_ParseTuple(
            args,
            "OOs#Os*iIO",
            &capsule_py,
            &self_py,
            &operation_name,
            &operation_name_len,
            &headers_py,
            &payload_buf,
            &message_type,
            &message_flags,
            &on_flush_py)) {
        return NULL;
    }

    struct continuation_binding *continuation = PyCapsule_GetPointer(capsule_py, s_capsule_name);
    if (!continuation) {
        return NULL;
    }

    if (continuation->self_py != NULL) {
        PyErr_SetString(PyExc_RuntimeError, "Continuation already activated");
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    bool success = false;
    struct aws_array_list headers;
    AWS_ZERO_STRUCT(headers);
    Py_INCREF(on_flush_py); /* Keep completion callback alive until it fires */

    continuation->self_py = self_py;
    Py_INCREF(continuation->self_py);

    if (!aws_py_event_stream_native_headers_init(&headers, headers_py)) {
        goto done;
    }

    struct aws_byte_buf payload = aws_byte_buf_from_array(payload_buf.buf, payload_buf.len);
    struct aws_event_stream_rpc_message_args msg_args = {
        .headers = headers.data,
        .headers_count = aws_array_list_length(&headers),
        .payload = &payload,
        .message_type = message_type,
        .message_flags = message_flags,
    };
    if (aws_event_stream_rpc_client_continuation_activate(
            continuation->native,
            aws_byte_cursor_from_array(operation_name, (size_t)operation_name_len),
            &msg_args,
            aws_py_event_stream_rpc_client_on_message_flush,
            on_flush_py)) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;

done:
    PyBuffer_Release(&payload_buf);
    if (aws_array_list_is_valid(&headers)) {
        aws_event_stream_headers_list_cleanup(&headers);
    }

    if (success) {
        Py_RETURN_NONE;
    }

    /* failed */
    Py_DECREF(on_flush_py);
    Py_CLEAR(continuation->self_py);

    return NULL;
}

PyObject *aws_py_event_stream_rpc_client_continuation_send_message(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *capsule_py;
    PyObject *headers_py;
    Py_buffer payload_buf; /* Py_buffers must be released after successful PyArg_ParseTuple() calls */
    int message_type;
    uint32_t message_flags;
    PyObject *on_flush_py;
    if (!PyArg_ParseTuple(
            args, "OOs*iIO", &capsule_py, &headers_py, &payload_buf, &message_type, &message_flags, &on_flush_py)) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    bool success = false;
    struct aws_array_list headers;
    AWS_ZERO_STRUCT(headers);

    /* Keep completion callback alive until it fires */
    Py_INCREF(on_flush_py);

    struct continuation_binding *continuation = PyCapsule_GetPointer(capsule_py, s_capsule_name);
    if (!continuation) {
        goto done;
    }

    if (!aws_py_event_stream_native_headers_init(&headers, headers_py)) {
        goto done;
    }

    struct aws_byte_buf payload = aws_byte_buf_from_array(payload_buf.buf, payload_buf.len);
    struct aws_event_stream_rpc_message_args msg_args = {
        .headers = headers.data,
        .headers_count = aws_array_list_length(&headers),
        .payload = &payload,
        .message_type = message_type,
        .message_flags = message_flags,
    };
    if (aws_event_stream_rpc_client_continuation_send_message(
            continuation->native, &msg_args, aws_py_event_stream_rpc_client_on_message_flush, on_flush_py)) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;

done:
    PyBuffer_Release(&payload_buf);
    if (aws_array_list_is_valid(&headers)) {
        aws_event_stream_headers_list_cleanup(&headers);
    }

    if (success) {
        Py_RETURN_NONE;
    }

    Py_DECREF(on_flush_py);
    return NULL;
}

PyObject *aws_py_event_stream_rpc_client_continuation_is_closed(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) {
        return NULL;
    }

    struct continuation_binding *continuation = PyCapsule_GetPointer(capsule, s_capsule_name);
    if (!continuation) {
        return NULL;
    }

    if (aws_event_stream_rpc_client_continuation_is_closed(continuation->native)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}
