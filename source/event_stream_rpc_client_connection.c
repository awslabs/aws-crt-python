/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "event_stream.h"

#include "io.h"

#include <aws/event-stream/event_stream_rpc_client.h>
#include <aws/io/socket.h>

struct connection_binding;
static void s_capsule_destructor(PyObject *capsule);
static void s_on_connection_setup(
    struct aws_event_stream_rpc_client_connection *native,
    int error_code,
    void *user_data);
static void s_on_connection_shutdown(
    struct aws_event_stream_rpc_client_connection *native,
    int error_code,
    void *user_data);
static void s_on_protocol_message(
    struct aws_event_stream_rpc_client_connection *native,
    const struct aws_event_stream_rpc_message_args *message_args,
    void *user_data);

static const char *s_capsule_name = "aws_event_stream_rpc_client_connection";

struct connection_binding {
    struct aws_event_stream_rpc_client_connection *native;

    /* This reference is solely used for invoking callbacks,
     * and is cleared after the final callback is invoked.
     * If it were not cleared, circular references between the python object
     * and its binding would prevent the GC from ever cleaning things up */
    PyObject *self_py;
};

struct aws_event_stream_rpc_client_connection *aws_py_get_event_stream_rpc_client_connection(PyObject *connection) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(connection, s_capsule_name, "ClientConnection", connection_binding);
}

PyObject *aws_py_event_stream_rpc_client_connection_connect(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *alloc = aws_py_get_allocator();

    const char *host_name;
    uint32_t port;
    PyObject *bootstrap_py;
    PyObject *socket_options_py;
    PyObject *tls_options_py;
    PyObject *connection_py;
    if (!PyArg_ParseTuple(
            args, "sIOOOO", &host_name, &port, &bootstrap_py, &socket_options_py, &tls_options_py, &connection_py)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct aws_socket_options socket_options;
    if (!aws_py_socket_options_init(&socket_options, socket_options_py)) {
        return NULL;
    }

    /* TLS options are optional */
    struct aws_tls_connection_options *tls_options = NULL;
    if (tls_options_py != Py_None) {
        tls_options = aws_py_get_tls_connection_options(tls_options_py);
        if (!tls_options) {
            return NULL;
        }
    }

    struct connection_binding *connection = aws_mem_calloc(alloc, 1, sizeof(struct connection_binding));
    PyObject *capsule = PyCapsule_New(connection, s_capsule_name, s_capsule_destructor);
    if (!capsule) {
        aws_mem_release(alloc, connection);
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    connection->self_py = connection_py;
    Py_INCREF(connection->self_py);

    /* Set _binding before calling connect() */
    if (PyObject_SetAttrString(connection_py, "_binding", capsule) != 0) {
        goto error;
    }

    /* Now that connection._binding holds reference to capsule, we can decref the creation reference */
    Py_CLEAR(capsule);

    struct aws_event_stream_rpc_client_connection_options conn_options = {
        .host_name = host_name,
        .port = port,
        .socket_options = &socket_options,
        .tls_options = tls_options,
        .bootstrap = bootstrap,
        .on_connection_setup = s_on_connection_setup,
        .on_connection_shutdown = s_on_connection_shutdown,
        .on_connection_protocol_message = s_on_protocol_message,
        .user_data = connection,
    };

    if (aws_event_stream_rpc_client_connection_connect(alloc, &conn_options)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    Py_RETURN_NONE;

error:
    /* clear circular reference */
    Py_CLEAR(connection->self_py);

    /* if capsule pointer still valid, this will invoke its destructor,
     * which will clean up anything inside of it */
    Py_CLEAR(capsule);
    return NULL;
}

static void s_on_connection_setup(
    struct aws_event_stream_rpc_client_connection *native,
    int error_code,
    void *user_data) {
    struct connection_binding *connection = user_data;

    AWS_FATAL_ASSERT(((bool)native != (bool)error_code) && "illegal event-stream connection args");

    if (native) {
        connection->native = native;
        aws_event_stream_rpc_client_connection_acquire(connection->native);
    }

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(connection->self_py, "_on_connection_setup", "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Close connection if unhandled exception occurs.
         * Note that callback might fail during application shutdown */
        AWS_LOGF_ERROR(
            AWS_LS_EVENT_STREAM_RPC_CLIENT,
            "id=%p: Exception in on_connection_setup() callback, closing connection.",
            (void *)connection->native);

        PyErr_WriteUnraisable(connection->self_py);
        if (native) {
            aws_event_stream_rpc_client_connection_close(connection->native, AWS_ERROR_CRT_CALLBACK_EXCEPTION);
        }
    }

    if (!native) {
        /* There will be no further callbacks, clear circular reference
         * so that python connection object can ever be GC'd */
        Py_CLEAR(connection->self_py);
    }

    PyGILState_Release(state);
}

static void s_on_connection_shutdown(
    struct aws_event_stream_rpc_client_connection *native,
    int error_code,
    void *user_data) {

    (void)native;
    struct connection_binding *connection = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(connection->self_py, "_on_connection_shutdown", "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(connection->self_py);
    }

    /* There will be no further callbacks, clear circular reference
     * so that python connection object can ever be GC'd */
    Py_CLEAR(connection->self_py);

    PyGILState_Release(state);
}

static void s_capsule_destructor(PyObject *capsule) {
    struct connection_binding *connection = PyCapsule_GetPointer(capsule, s_capsule_name);
    aws_event_stream_rpc_client_connection_release(connection->native);
    aws_mem_release(aws_py_get_allocator(), connection);
}

static void s_on_protocol_message(
    struct aws_event_stream_rpc_client_connection *native,
    const struct aws_event_stream_rpc_message_args *message_args,
    void *user_data) {

    (void)native;
    struct connection_binding *connection = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *headers = NULL;
    PyObject *result = NULL;

    headers = aws_py_event_stream_python_headers_create(message_args->headers, message_args->headers_count);
    if (!headers) {
        PyErr_WriteUnraisable(connection->self_py);
        goto done;
    }

    result = PyObject_CallMethod(
        connection->self_py,
        "_on_protocol_message",
        "(Oy#iI)",
        headers,
        message_args->payload->buffer,
        message_args->payload->len,
        message_args->message_type,
        message_args->message_flags);
    if (!result) {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(connection->self_py);
        goto done;
    }

done:
    Py_XDECREF(headers);
    Py_XDECREF(result);
    PyGILState_Release(state);
}

PyObject *aws_py_event_stream_rpc_client_connection_close(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) {
        return NULL;
    }

    struct connection_binding *connection = PyCapsule_GetPointer(capsule, s_capsule_name);
    if (!connection) {
        return NULL;
    }

    aws_event_stream_rpc_client_connection_close(connection->native, AWS_OP_SUCCESS);
    Py_RETURN_NONE;
}

PyObject *aws_py_event_stream_rpc_client_connection_is_open(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) {
        return NULL;
    }

    struct connection_binding *connection = PyCapsule_GetPointer(capsule, s_capsule_name);
    if (!connection) {
        return NULL;
    }

    if (aws_event_stream_rpc_client_connection_is_open(connection->native)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

void aws_py_event_stream_rpc_client_on_message_flush(int error_code, void *user_data) {
    PyObject *on_flush_py = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallFunction(on_flush_py, "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(on_flush_py);
    }

    /* Release reference to completion callback */
    Py_DECREF(on_flush_py);

    PyGILState_Release(state);
}

PyObject *aws_py_event_stream_rpc_client_connection_send_protocol_message(PyObject *self, PyObject *args) {
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

    struct connection_binding *connection = PyCapsule_GetPointer(capsule_py, s_capsule_name);
    if (!connection) {
        goto done;
    }

    /* OPTIMIZATION IDEA: Currently, we're deep-copying byte_bufs and strings
     * into the C headers. We did this because it was simple (and headers
     * shouldn't be gigantic). Since send_protocol_message() ALSO copies
     * everything we could, instead, create non-owning C headers here.
     * It would be more complex because we'd need to track a
     * list of Py_buffer to release afterwards. */
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
    if (aws_event_stream_rpc_client_connection_send_protocol_message(
            connection->native, &msg_args, aws_py_event_stream_rpc_client_on_message_flush, on_flush_py)) {
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
