/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "event_stream.h"

#include <aws/event-stream/event_stream_rpc_client.h>

struct continuation_binding;
static void s_continuation_capsule_destructor(PyObject *capsule);
static void s_continuation_destroy_if_ready(struct continuation_binding *continuation);
static void s_on_continuation_closed(struct aws_event_stream_rpc_client_continuation_token *native, void *user_data);
static void s_on_continuation_message(
    struct aws_event_stream_rpc_client_continuation_token *native,
    const struct aws_event_stream_rpc_message_args *message_args,
    void *user_data);

static const char *s_capsule_name = "aws_event_stream_rpc_client_continuation_token";

struct continuation_binding {
    struct aws_event_stream_rpc_client_continuation_token *native;

    /* Binding cannot be destroyed until:
     * capsule has been destroyed AND
     * ((continuation was activated AND closed) OR (never activated at all)) */
    bool capsule_destroyed;
    bool has_activated;
    bool has_closed;

    PyObject *on_message;
    PyObject *on_closed;
};

struct aws_event_stream_rpc_client_continuation_token *aws_py_get_event_stream_rpc_client_continuation(
    PyObject *continuation) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(continuation, s_capsule_name, "ClientContinuation", continuation_binding);
}

PyObject *aws_py_event_stream_rpc_client_connection_new_stream(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *connection_py;
    PyObject *on_message_py;
    PyObject *on_closed_py;
    if (!PyArg_ParseTuple(args, "OOO", &connection_py, &on_message_py, &on_closed_py)) {
        return NULL;
    }

    struct aws_event_stream_rpc_client_connection *native_connection =
        aws_py_get_event_stream_rpc_client_connection(connection_py);
    if (!native_connection) {
        return NULL;
    }

    struct continuation_binding *continuation =
        aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct continuation_binding));
    PyObject *capsule = PyCapsule_New(continuation, s_capsule_name, s_continuation_capsule_destructor);
    if (!capsule) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    continuation->on_message = on_message_py;
    Py_INCREF(continuation->on_message);
    continuation->on_closed = on_closed_py;
    Py_INCREF(continuation->on_closed);

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

    AWS_FATAL_ASSERT(
        continuation->has_activated && "Illegal for on_continuation_close to fire without having activated");
    AWS_FATAL_ASSERT(!continuation->has_closed && "Illegal for on_continuation_close to fire twice");
    continuation->has_closed = true;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallFunction(continuation->on_closed, "()");
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    s_continuation_destroy_if_ready(continuation);
    PyGILState_Release(state);
}

static void s_continuation_capsule_destructor(PyObject *capsule) {
    struct continuation_binding *continuation = PyCapsule_GetPointer(capsule, s_capsule_name);
    continuation->capsule_destroyed = true;
    s_continuation_destroy_if_ready(continuation);
}

static void s_continuation_destroy_if_ready(struct continuation_binding *continuation) {
    bool destroy;
    if (continuation->native) {
        if (continuation->capsule_destroyed) {
            if (continuation->has_activated) {
                if (continuation->has_closed) {
                    /* python class has been GC'd and continuation is complete */
                    destroy = true;
                } else {
                    /* python class been GC'd but continuation hasn't finished */
                    destroy = false;
                }
            } else {
                /* capsule has been GC'd and continuation was never activated */
                destroy = true;
            }
        } else {
            /* capsule still alive */
            destroy = false;
        }
    } else {
        /* native continuation creation failed */
        destroy = true;
    }

    if (destroy) {
        aws_event_stream_rpc_client_continuation_release(continuation->native);
        Py_XDECREF(continuation->on_message);
        Py_XDECREF(continuation->on_closed);
        aws_mem_release(aws_py_get_allocator(), continuation);
    }
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

    PyObject *result = PyObject_CallFunction(
        continuation->on_message,
        "(Oy#iI)",
        /* NOTE: if headers_create() returns NULL, then PyObject_CallFunction() fails too, which is convenient */
        aws_py_event_stream_python_headers_create(message_args->headers, message_args->headers_count),
        message_args->payload->buffer,
        message_args->payload->len,
        message_args->message_type,
        message_args->message_flags);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());

        /* TODO: Should we close the stream on an unhandled exception?
         * If so, do we differentiate between internal failure and failure stemming from the user's callback? */
    }

    PyGILState_Release(state);
}

PyObject *aws_py_event_stream_rpc_client_continuation_activate(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *capsule_py;
    const char *operation_name;
    Py_ssize_t operation_name_len;
    PyObject *headers_py;
    Py_buffer payload_buf; /* Py_buffers must be released after successful PyArg_ParseTuple() calls */
    int message_type;
    uint32_t message_flags;
    PyObject *on_flush_py;
    if (!PyArg_ParseTuple(
            args,
            "Os#Os*iIO",
            &capsule_py,
            &operation_name,
            &operation_name_len,
            &headers_py,
            &payload_buf,
            &message_type,
            &message_flags,
            &on_flush_py)) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    bool success = false;
    struct aws_array_list headers;
    AWS_ZERO_STRUCT(headers);
    bool has_activated_prev_value = false;
    Py_INCREF(on_flush_py); /* Keep completion callback alive until it fires */

    struct continuation_binding *continuation = PyCapsule_GetPointer(capsule_py, s_capsule_name);
    if (!continuation) {
        goto done;
    }

    has_activated_prev_value = continuation->has_activated;
    continuation->has_activated = true;

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
    if (continuation) {
        continuation->has_activated = has_activated_prev_value;
    }
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
