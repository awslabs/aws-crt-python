/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "websocket.h"

#include "http.h"
#include "io.h"

#include <aws/http/proxy.h>
#include <aws/http/request_response.h>
#include <aws/http/websocket.h>
#include <aws/io/socket.h>

static const char *s_websocket_capsule_name = "aws_websocket";

static void s_websocket_on_connection_setup(
    const struct aws_websocket_on_connection_setup_data *setup,
    void *user_data);

static void s_websocket_on_connection_shutdown(struct aws_websocket *websocket, int error_code, void *user_data);

static bool s_websocket_on_incoming_frame_begin(
    struct aws_websocket *websocket,
    const struct aws_websocket_incoming_frame *frame,
    void *user_data);

static bool s_websocket_on_incoming_frame_payload(
    struct aws_websocket *websocket,
    const struct aws_websocket_incoming_frame *frame,
    struct aws_byte_cursor data,
    void *user_data);

static bool s_websocket_on_incoming_frame_complete(
    struct aws_websocket *websocket,
    const struct aws_websocket_incoming_frame *frame,
    int error_code,
    void *user_data);

/* When WebSocket._binding is GC'd, release the native websocket pointer.
 * It will close (if necessary) on its way to the grave */
static void s_websocket_capsule_destructor(PyObject *capsule) {
    struct aws_websocket *websocket = PyCapsule_GetPointer(capsule, s_websocket_capsule_name);
    aws_websocket_release(websocket);
}

/* Kick off websocket connection.
 * WebSocket._binding does not get returned from this function,
 * it gets delivered later via the _WebSocketCore._on_connection_setup() callback */
PyObject *aws_py_websocket_client_connect(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor host;    /* s# */
    uint16_t port;                  /* H */
    PyObject *handshake_request_py; /* O */
    PyObject *bootstrap_py;         /* O */
    PyObject *socket_options_py;    /* O */
    PyObject *tls_options_py;       /* O */
    PyObject *proxy_options_py;     /* O */
    int manage_read_window;         /* p - boolean predicate */
    Py_ssize_t initial_read_window; /* n */
    PyObject *websocket_core_py;    /* O */

    if (!PyArg_ParseTuple(
            args,
            "s#HOOOOOpnO",
            &host.ptr,
            &host.len,
            &port,
            &handshake_request_py,
            &bootstrap_py,
            &socket_options_py,
            &tls_options_py,
            &proxy_options_py,
            &manage_read_window,
            &initial_read_window,
            &websocket_core_py)) {
        return NULL;
    }

    /* First, wrangle args that don't require any cleanup if things go wrong... */

    /* required bootstrap */
    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (bootstrap == NULL) {
        return NULL;
    }

    /* required socket_options */
    struct aws_socket_options socket_options;
    if (aws_py_socket_options_init(&socket_options, socket_options_py) == false) {
        return NULL;
    }

    /* optional tls_options */
    struct aws_tls_connection_options *tls_options = NULL;
    if (tls_options_py != Py_None) {
        tls_options = aws_py_get_tls_connection_options(tls_options_py);
        if (tls_options == NULL) {
            return NULL;
        }
    }

    /* optional proxy_options */
    bool has_proxy_options = proxy_options_py != Py_None;
    struct aws_http_proxy_options proxy_options;
    if (has_proxy_options) {
        if (aws_py_http_proxy_options_init(&proxy_options, proxy_options_py) == false) {
            return NULL;
        }
    }

    /* required handshake_request */
    struct aws_http_message *handshake_request = aws_py_get_http_message(handshake_request_py);
    if (handshake_request == NULL) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur... */

    /* keep _WebSocketCore alive for lifetime of aws_websocket */
    Py_INCREF(websocket_core_py);

    struct aws_websocket_client_connection_options options = {
        .allocator = aws_py_get_allocator(),
        .bootstrap = bootstrap,
        .socket_options = &socket_options,
        .tls_options = tls_options,
        .proxy_options = has_proxy_options ? &proxy_options : NULL,
        .host = host,
        .port = port,
        .handshake_request = handshake_request,
        .initial_window_size = (size_t)initial_read_window, /* already checked it was non-negative out in python */
        .user_data = websocket_core_py,
        .on_connection_setup = s_websocket_on_connection_setup,
        .on_connection_shutdown = s_websocket_on_connection_shutdown,
        .on_incoming_frame_begin = s_websocket_on_incoming_frame_begin,
        .on_incoming_frame_payload = s_websocket_on_incoming_frame_payload,
        .on_incoming_frame_complete = s_websocket_on_incoming_frame_complete,
        .manual_window_management = manage_read_window != 0,
    };
    if (aws_websocket_client_connect(&options) != AWS_OP_SUCCESS) {
        PyErr_SetAwsLastError();
        goto error;
    }

    /* Success! */
    Py_RETURN_NONE;

error:
    Py_DECREF(websocket_core_py);
    return NULL;
}

/* Completion callback for websocket_client_connect().
 * Wrangle args and fire _WebSocketCore._on_connection_setup().
 *
 * DIATRIBE ON ERROR HANDLING:
 * Wrangling args from C->Python takes a lot of function calls that could THEORETICALLY fail.
 * But we MUST fire the completion callback or the user's code would just hang.
 *
 * Attempting to handle all theoretical arg-wrangling errors would add a TON of complexity, such as:
 * - switch callback to report failure instead of success
 * - cleanup half-initialized resources (shut down websocket, cleanup half-initialized lists)
 * - ability to report pure python exception, in addition to C error_code, in callback
 * - suppress further callbacks from C as websocket shuts down,
 *   to maintain contract of "if init fails, then no further callbacks"
 *
 * I'm making a judgement call to just make these theoretical failures fatal.
 * If there's a bug, it will be glaringly obvious, and simple to fix.
 * This seems better than complicating things with tons of error-handling code
 * that we can't actually check (and so may not actually work).
 */
static void s_websocket_on_connection_setup(
    const struct aws_websocket_on_connection_setup_data *setup,
    void *user_data) {

    /* sanity check: websocket XOR error_code is set. both cannot be set. both cannot be unset */
    AWS_FATAL_ASSERT((setup->websocket != NULL) ^ (setup->error_code != 0));

    /* userdata is _WebSocketCore */
    PyObject *websocket_core_py = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *websocket_binding_py = NULL;
    if (setup->websocket) {
        websocket_binding_py =
            PyCapsule_New(setup->websocket, s_websocket_capsule_name, s_websocket_capsule_destructor);
        AWS_FATAL_ASSERT(websocket_binding_py && "capsule allocation failed");
    }

    /* Any of the handshake_response variables could be NULL */

    PyObject *status_code_py = NULL;
    if (setup->handshake_response_status != NULL) {
        status_code_py = PyLong_FromLong(*setup->handshake_response_status);
        AWS_FATAL_ASSERT(status_code_py && "status code allocation failed");
    }

    PyObject *headers_py = NULL;
    if (setup->handshake_response_header_array != NULL) {
        headers_py = PyList_New((Py_ssize_t)setup->num_handshake_response_headers);
        AWS_FATAL_ASSERT(headers_py && "header list allocation failed");
        for (size_t i = 0; i < setup->num_handshake_response_headers; ++i) {
            const struct aws_http_header *header_i = &setup->handshake_response_header_array[i];
            PyObject *tuple_py = PyTuple_New(2);
            AWS_FATAL_ASSERT(tuple_py && "header tuple allocation failed");

            PyObject *name_py = PyUnicode_FromAwsByteCursor(&header_i->name);
            AWS_FATAL_ASSERT(name_py && "header name wrangling failed");
            PyTuple_SetItem(tuple_py, 0, name_py); /* Steals a reference */

            PyObject *value_py = PyUnicode_FromAwsByteCursor(&header_i->value);
            AWS_FATAL_ASSERT(value_py && "header value wrangling failed");
            PyTuple_SetItem(tuple_py, 1, value_py); /* Steals a reference */

            PyList_SetItem(headers_py, i, tuple_py); /* Steals a reference */
        }
    }

    PyObject *body_py = NULL;
    if (setup->handshake_response_body != NULL) {
        /* AWS APIs are fine with NULL as the address of a 0-length array,
         * but python APIs requires that it be non-NULL */
        const char *ptr = setup->handshake_response_body->ptr ? (const char *)setup->handshake_response_body->ptr : "";
        body_py = PyBytes_FromStringAndSize(ptr, (Py_ssize_t)setup->handshake_response_body->len);
        AWS_FATAL_ASSERT(body_py && "response body allocation failed");
    }

    PyObject *result = PyObject_CallMethod(
        websocket_core_py,
        "_on_connection_setup",
        "(iOOOO)",
        /* i */ setup->error_code,
        /* O */ websocket_binding_py ? websocket_binding_py : Py_None,
        /* O */ status_code_py ? status_code_py : Py_None,
        /* O */ headers_py ? headers_py : Py_None,
        /* O */ body_py ? body_py : Py_None);

    if (result) {
        Py_DECREF(result);
    } else {
        /* _WebSocketCore._on_connection_setup() runs the user's callback in a try/except
         * So any exception that leaks out is an unexpected bug in our code.
         * Make it fatal, we have no graceful way to deal with this. */
        PyErr_WriteUnraisable(websocket_core_py);
        AWS_FATAL_ASSERT(0 && "Failed to invoke WebSocket on_connection_setup callback");
    }

    Py_XDECREF(websocket_binding_py);
    Py_XDECREF(status_code_py);
    Py_XDECREF(headers_py);
    Py_XDECREF(body_py);

    /* If setup failed, there will be no further callbacks, so release _WebSocketCore */
    if (setup->error_code != 0) {
        Py_DECREF(websocket_core_py);
    }

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

static void s_websocket_on_connection_shutdown(struct aws_websocket *websocket, int error_code, void *user_data) {
    (void)websocket;

    /* userdata is _WebSocketCore */
    PyObject *websocket_core_py = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallMethod(websocket_core_py, "_on_connection_shutdown", "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* _WebSocketCore._on_connection_shutdown() runs the user's callback in a try/except.
         * So any exception that leaks out is an unexpected bug in our code.
         * Make it fatal, we have no graceful way to deal with this. */
        PyErr_WriteUnraisable(websocket_core_py);
        AWS_FATAL_ASSERT(0 && "Failed to invoke WebSocket on_connection_shutdown callback");
    }

    /* Release _WebSocketCore, there will be no further callbacks */
    Py_DECREF(websocket_core_py);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

static bool s_websocket_on_incoming_frame_begin(
    struct aws_websocket *websocket,
    const struct aws_websocket_incoming_frame *frame,
    void *user_data) {

    (void)websocket;

    /* userdata is _WebSocketCore */
    PyObject *websocket_core_py = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallMethod(
        websocket_core_py,
        "_on_incoming_frame_begin",
        "(iKO)",
        frame->opcode,
        frame->payload_length,
        frame->fin ? Py_True : Py_False);

    /* If the user's callback raises an exception, we catch it and return False to C... */
    if (result == NULL) {
        /* ... so any exception that leaks out is an unexpected bug in our code.
         * Make it fatal, we have no graceful way to deal with this. */
        PyErr_WriteUnraisable(websocket_core_py);
        AWS_FATAL_ASSERT(0 && "Failed to invoke WebSocket on_incoming_frame_begin callback");
    }

    bool success = PyObject_IsTrue(result);
    Py_DECREF(result);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return success;
}

static bool s_websocket_on_incoming_frame_payload(
    struct aws_websocket *websocket,
    const struct aws_websocket_incoming_frame *frame,
    struct aws_byte_cursor data,
    void *user_data) {

    (void)websocket;
    (void)frame;

    /* userdata is _WebSocketCore */
    PyObject *websocket_core_py = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallMethod(websocket_core_py, "_on_incoming_frame_payload", "(y#)", data.ptr, data.len);

    /* If the user's callback raises an exception, we catch it and return False to C... */
    if (result == NULL) {
        /* ... so any exception that leaks out is an unexpected bug in our code.
         * Make it fatal, we have no graceful way to deal with this. */
        PyErr_WriteUnraisable(websocket_core_py);
        AWS_FATAL_ASSERT(0 && "Failed to invoke WebSocket on_incoming_frame_payload callback");
    }

    bool success = PyObject_IsTrue(result);
    Py_DECREF(result);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return success;
}

static bool s_websocket_on_incoming_frame_complete(
    struct aws_websocket *websocket,
    const struct aws_websocket_incoming_frame *frame,
    int error_code,
    void *user_data) {

    (void)websocket;
    (void)frame;

    /* userdata is _WebSocketCore */
    PyObject *websocket_core_py = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallMethod(websocket_core_py, "_on_incoming_frame_complete", "(i)", error_code);

    /* If the user's callback raises an exception, we catch it and return False to C... */
    if (result == NULL) {
        /* ... so any exception that leaks out is an unexpected bug in our code.
         * Make it fatal, we have no graceful way to deal with this. */
        PyErr_WriteUnraisable(websocket_core_py);
        AWS_FATAL_ASSERT(0 && "Failed to invoke WebSocket on_incoming_frame_complete callback");
    }

    bool success = PyObject_IsTrue(result);
    Py_DECREF(result);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return success;
}

PyObject *aws_py_websocket_close(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *binding_py; /* O */
    if (!PyArg_ParseTuple(args, "O", &binding_py)) {
        return NULL;
    }

    struct aws_websocket *websocket = PyCapsule_GetPointer(binding_py, s_websocket_capsule_name);
    if (!websocket) {
        return NULL;
    }

    aws_websocket_close(websocket, false /*free_scarce_resources_immediately*/);

    Py_RETURN_NONE;
}

/**
 * This stays alive for the duration of a send_frame operation.
 * It streams the payload data, and fires the completion callback.
 */
struct websocket_send_op {
    /* Py_buffer lets us hold onto Python data and read it without holding the GIL */
    Py_buffer payload_buffer;

    /* this cursor tracks our progress streaming the payload */
    struct aws_byte_cursor payload_cursor;

    PyObject *on_complete_py;
};

static void s_websocket_send_op_destroy(struct websocket_send_op *send_op) {
    if (send_op == NULL) {
        return;
    }

    if (send_op->payload_buffer.buf != NULL) {
        PyBuffer_Release(&send_op->payload_buffer);
    }

    Py_XDECREF(send_op->on_complete_py);

    aws_mem_release(aws_py_get_allocator(), send_op);
}

static bool s_websocket_stream_outgoing_payload(
    struct aws_websocket *websocket,
    struct aws_byte_buf *out_buf,
    void *user_data) {

    (void)websocket;
    struct websocket_send_op *send_op = user_data;

    aws_byte_buf_write_to_capacity(out_buf, &send_op->payload_cursor);
    return true;
}

static void s_websocket_on_send_frame_complete(struct aws_websocket *websocket, int error_code, void *user_data) {
    (void)websocket;

    struct websocket_send_op *send_op = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(send_op->on_complete_py, "(i)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* WebSocket.send_frame.on_complete() runs the user's callback in a try/except.
         * So any exception that leaks out is an unexpected bug in our code.
         * Make it fatal, we have no graceful way to deal with this. */
        PyErr_WriteUnraisable(send_op->on_complete_py);
        AWS_FATAL_ASSERT(0 && "Failed to invoke WebSocket.send_frame()'s on_complete callback");
    }

    s_websocket_send_op_destroy(send_op);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

PyObject *aws_py_websocket_send_frame(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *binding_py;     /* O */
    uint8_t opcode;           /* b */
    Py_buffer payload_buffer; /* z* */
    int fin;                  /* p - boolean predicate */
    PyObject *on_complete_py; /* O */

    if (!PyArg_ParseTuple(args, "Obz*pO", &binding_py, &opcode, &payload_buffer, &fin, &on_complete_py)) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur (Py_buffers must always be released) ... */

    struct websocket_send_op *send_op = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct websocket_send_op));
    send_op->payload_buffer = payload_buffer;
    send_op->payload_cursor = aws_byte_cursor_from_array(payload_buffer.buf, payload_buffer.len);
    Py_INCREF(on_complete_py);
    send_op->on_complete_py = on_complete_py;

    struct aws_websocket *websocket = PyCapsule_GetPointer(binding_py, s_websocket_capsule_name);
    if (!websocket) {
        goto error;
    }

    struct aws_websocket_send_frame_options options = {
        .payload_length = (uint64_t)payload_buffer.len,
        .user_data = send_op,
        .stream_outgoing_payload = s_websocket_stream_outgoing_payload,
        .on_complete = s_websocket_on_send_frame_complete,
        .opcode = opcode,
        .fin = fin,
    };

    if (aws_websocket_send_frame(websocket, &options)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    /* Success! */
    Py_RETURN_NONE;

error:
    s_websocket_send_op_destroy(send_op);
    return NULL;
}

PyObject *aws_py_websocket_increment_read_window(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *binding_py; /* O */
    Py_ssize_t size;      /* n */

    if (!PyArg_ParseTuple(args, "On", &binding_py, &size)) {
        return NULL;
    }

    struct aws_websocket *websocket = PyCapsule_GetPointer(binding_py, s_websocket_capsule_name);
    if (!websocket) {
        return NULL;
    }

    /* already checked that size was non-negative out in python */
    aws_websocket_increment_read_window(websocket, (size_t)size);
    Py_RETURN_NONE;
}

PyObject *aws_py_websocket_create_handshake_request(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor host; /* s# */
    struct aws_byte_cursor path; /* s# */

    if (!PyArg_ParseTuple(args, "s#s#", &host.ptr, &host.len, &path.ptr, &path.len)) {
        return NULL;
    }

    /* This function will return a tuple containing:
     * 1) the binding for an HttpRequest
     * 2) the binding for an HttpHeaders */
    bool success = false;
    struct aws_http_message *request = NULL;
    PyObject *tuple_py = NULL;

    request = aws_http_message_new_websocket_handshake_request(aws_py_get_allocator(), path, host);
    if (!request) {
        PyErr_SetAwsLastError();
        goto cleanup;
    }

    tuple_py = PyTuple_New(2);
    if (!tuple_py) {
        goto cleanup;
    }

    PyObject *request_binding_py = aws_py_http_message_new_request_from_native(request);
    if (!request_binding_py) {
        goto cleanup;
    }
    PyTuple_SetItem(tuple_py, 0, request_binding_py); /* steals reference to request_binding_py */

    PyObject *headers_binding_py = aws_py_http_headers_new_from_native(aws_http_message_get_headers(request));
    if (!headers_binding_py) {
        goto cleanup;
    }
    PyTuple_SetItem(tuple_py, 1, headers_binding_py); /* steals reference to headers_binding_py */

    /* Success! */
    success = true;

cleanup:
    aws_http_message_release(request);
    if (success) {
        return tuple_py;
    } else {
        Py_XDECREF(tuple_py);
        return NULL;
    }
}
