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
    struct aws_websocket *websocket,
    int error_code,
    int handshake_response_status,
    const struct aws_http_header *handshake_response_header_array,
    size_t num_handshake_response_headers,
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
    int enable_read_backpressure;   /* p - boolean predicate */
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
            &enable_read_backpressure,
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

    /* required window size */
    if (initial_read_window < 0) {
        PyErr_Format(PyExc_ValueError, "'initial_read_window' cannot be negative");
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
        .initial_window_size = (size_t)initial_read_window,
        .user_data = websocket_core_py,
        .on_connection_setup = s_websocket_on_connection_setup,
        .on_connection_shutdown = s_websocket_on_connection_shutdown,
        .on_incoming_frame_begin = s_websocket_on_incoming_frame_begin,
        .on_incoming_frame_payload = s_websocket_on_incoming_frame_payload,
        .on_incoming_frame_complete = s_websocket_on_incoming_frame_complete,
        .manual_window_management = enable_read_backpressure != 0,
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
 * This seems better than significantly complicating things with a ton of code
 * we can't actually check and may not actually work.
 */
static void s_websocket_on_connection_setup(
    struct aws_websocket *websocket,
    int error_code,
    int handshake_response_status,
    const struct aws_http_header *handshake_response_header_array,
    size_t num_handshake_response_headers,
    void *user_data) {

    /* sanity check: websocket XOR error_code is set. both cannot be set. both cannot be unset */
    AWS_FATAL_ASSERT((websocket != NULL) ^ (error_code != 0));

    /* userdata is _WebSocketCore */
    PyObject *websocket_core_py = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *websocket_binding_py = NULL;
    if (websocket) {
        websocket_binding_py = PyCapsule_New(websocket, s_websocket_capsule_name, s_websocket_capsule_destructor);
        AWS_FATAL_ASSERT(websocket_binding_py && "capsule allocation failed");
    }

    PyObject *headers_py = NULL;
    if (num_handshake_response_headers > 0) {
        headers_py = PyList_New((Py_ssize_t)num_handshake_response_headers);
        AWS_FATAL_ASSERT(headers_py && "header list allocation failed");
        for (size_t i = 0; i < num_handshake_response_headers; ++i) {
            const struct aws_http_header *header_i = &handshake_response_header_array[i];
            PyObject *tuple_py = PyTuple_New(2);
            AWS_FATAL_ASSERT(tuple_py && "header tuple allocation failed");

            PyObject *name_py = PyUnicode_FromAwsByteCursor(&header_i->name);
            AWS_FATAL_ASSERT(name_py && "header name wrangling failed");
            PyTuple_SET_ITEM(tuple_py, 0, name_py);

            PyObject *value_py = PyUnicode_FromAwsByteCursor(&header_i->value);
            AWS_FATAL_ASSERT(value_py && "header value wrangling failed");
            PyTuple_SET_ITEM(tuple_py, 1, value_py);

            PyList_SET_ITEM(headers_py, i, tuple_py);
        }
    }

    PyObject *result = PyObject_CallMethod(
        websocket_core_py,
        "_on_connection_setup",
        "(iOiO)",
        error_code,
        websocket_binding_py ? websocket_binding_py : Py_None,
        handshake_response_status,
        headers_py ? headers_py : Py_None);

    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    Py_XDECREF(websocket_binding_py);
    Py_XDECREF(headers_py);

    /* If setup failed, there will be no further callbacks, so release _WebSocketCore */
    if (error_code != 0) {
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
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    /* Release _WebSocketCore, there will be no further callbacks */
    Py_DECREF(websocket_core_py);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/}

    static bool s_websocket_on_incoming_frame_begin(
        struct aws_websocket *websocket,
        const struct aws_websocket_incoming_frame *frame,
        void *user_data) {

        /* TODO implement */
        (void)websocket;
        (void)frame;
        (void)user_data;
        return false;
    }

    static bool s_websocket_on_incoming_frame_payload(
        struct aws_websocket *websocket,
        const struct aws_websocket_incoming_frame *frame,
        struct aws_byte_cursor data,
        void *user_data) {

        /* TODO implement */
        (void)websocket;
        (void)frame;
        (void)data;
        (void)user_data;
        return false;
    }

    static bool s_websocket_on_incoming_frame_complete(
        struct aws_websocket *websocket,
        const struct aws_websocket_incoming_frame *frame,
        int error_code,
        void *user_data) {

        /* TODO implement */
        (void)websocket;
        (void)frame;
        (void)error_code;
        (void)user_data;
        return false;
    }

    PyObject *aws_py_websocket_close(PyObject *self, PyObject *args) {
        /* TODO implement */
        (void)self;
        (void)args;
        return NULL;
    }

    PyObject *aws_py_websocket_send_frame(PyObject *self, PyObject *args) {
        /* TODO implement */
        (void)self;
        (void)args;
        return NULL;
    }

    PyObject *aws_py_websocket_increment_read_window(PyObject *self, PyObject *args) {
        /* TODO implement */
        (void)self;
        (void)args;
        return NULL;
    }

    PyObject *aws_py_websocket_create_handshake_request(PyObject *self, PyObject *args) {
        /* TODO implement */
        (void)self;
        (void)args;
        return NULL;
    }