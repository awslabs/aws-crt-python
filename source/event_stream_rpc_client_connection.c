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
static void s_connection_destroy_if_ready(struct connection_binding *connection);
static int s_on_connection_setup(
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
    bool shutdown_complete;
    bool capsule_destroyed;

    PyObject *on_setup;
    PyObject *on_shutdown;
    PyObject *on_protocol_message;
};

PyObject *aws_py_event_stream_rpc_client_connection_connect(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *alloc = aws_py_get_allocator();

    const char *host_name;
    uint16_t port;
    PyObject *bootstrap_py;
    PyObject *socket_options_py;
    PyObject *tls_options_py;
    PyObject *on_setup_py;
    PyObject *on_shutdown_py;
    PyObject *on_message_py;
    if (!PyArg_ParseTuple(
            args,
            "sHOOOOOO",
            &host_name,
            &port,
            &bootstrap_py,
            &socket_options_py,
            &tls_options_py,
            &on_setup_py,
            &on_shutdown_py,
            &on_message_py)) {
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

    connection->on_setup = on_setup_py;
    Py_INCREF(connection->on_setup);
    connection->on_shutdown = on_shutdown_py;
    Py_INCREF(connection->on_shutdown);
    connection->on_protocol_message = on_message_py;
    Py_INCREF(connection->on_protocol_message);

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

    return capsule;

error:
    /* capsule's destructor will clean up anything inside of it */
    Py_DECREF(capsule);
    return NULL;
}

static int s_on_connection_setup(
    struct aws_event_stream_rpc_client_connection *native,
    int error_code,
    void *user_data) {

    struct connection_binding *connection = user_data;
    connection->native = native;

    AWS_FATAL_ASSERT(!(native && error_code) && "illegal for event-stream connection to both succeed and fail");
    AWS_FATAL_ASSERT(connection->on_setup && "illegal for event-stream connection setup to fire twice");

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallFunction(connection->on_setup, "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    /* on_setup callback has a captured reference to python connection object.
     * Need to clear it so that its refcount can ever reach zero */
    Py_CLEAR(connection->on_setup);
    PyGILState_Release(state);

    return AWS_OP_SUCCESS; /* Calling code never actually checks this, so always returning SUCCESS */
}

static void s_on_connection_shutdown(
    struct aws_event_stream_rpc_client_connection *native,
    int error_code,
    void *user_data) {

    (void)native;
    struct connection_binding *connection = user_data;

    AWS_FATAL_ASSERT(!connection->shutdown_complete && "illegal for event-stream connection shutdown to fire twice");

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallFunction(connection->on_shutdown, "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    connection->shutdown_complete = true;
    s_connection_destroy_if_ready(connection);
    PyGILState_Release(state);
}

static void s_capsule_destructor(PyObject *capsule) {
    struct connection_binding *connection = PyCapsule_GetPointer(capsule, s_capsule_name);
    connection->capsule_destroyed = true;
    s_connection_destroy_if_ready(connection);
}

static void s_connection_destroy_if_ready(struct connection_binding *connection) {
    bool destroy;

    if (connection->native) {
        if (connection->capsule_destroyed) {
            if (connection->shutdown_complete) {
                /* python class has been GC'd and native connection has finished shutdown */
                destroy = true;
            } else {
                /* python class has been GC'd but native connection still neeeds to shut down */
                aws_event_stream_rpc_client_connection_close(connection->native, AWS_ERROR_SUCCESS);
                destroy = false;
            }
        } else {
            /* native connection has shut down, but python class still exists */
            destroy = false;
        }
    } else {
        /* native connection setup failed */
        destroy = true;
    }

    if (destroy) {
        Py_XDECREF(connection->on_setup);
        Py_XDECREF(connection->on_shutdown);
        Py_XDECREF(connection->on_protocol_message);
        aws_event_stream_rpc_client_connection_release(connection->native);
        aws_mem_release(aws_py_get_allocator(), connection);
    }
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

    /* We always want to deliver bytes to python user, even if the length is 0.
     * But PyObject_CallFunction() with "y#" will convert a NULL ptr to None instead of 0-length bytes.
     * Therefore, if message_args->payload_buffer is NULL, pass some other valid ptr instead. */
    const char *payload_ptr = (void *)message_args->payload->buffer;
    if (payload_ptr == NULL) {
        payload_ptr = "";
    }

    PyObject *result = PyObject_CallFunction(
        connection->on_protocol_message,
        "(Oy#iI)",
        /* NOTE: if headers_create() returns NULL, then PyObject_CallFunction() fails too, which is convenient */
        aws_py_event_stream_python_headers_create(message_args->headers, message_args->headers_count),
        payload_ptr,
        message_args->payload->len,
        message_args->message_type,
        message_args->message_flags);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());

        /* TODO: Should we close the connection on an unhandled exception?
         * If so, do we differentiate between internal failure and failure stemming from the user's callback? */
    }

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

    if (aws_event_stream_rpc_client_connection_is_closed(connection->native)) {
        Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
}

/* Invoked when send_protocol_message() completes */
static void s_on_protocol_message_flush(int error_code, void *user_data) {
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
        PyErr_WriteUnraisable(PyErr_Occurred());
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
            connection->native, &msg_args, s_on_protocol_message_flush, on_flush_py)) {
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
