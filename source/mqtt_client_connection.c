/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "mqtt_client_connection.h"
#include "mqtt5_client.h"

#include "http.h"
#include "io.h"
#include "mqtt_client.h"

#include <aws/mqtt/client.h>

#include <aws/http/connection.h>
#include <aws/http/proxy.h>
#include <aws/http/request_response.h>

#include <aws/io/channel.h>
#include <aws/io/channel_bootstrap.h>
#include <aws/io/event_loop.h>
#include <aws/io/host_resolver.h>
#include <aws/io/socket.h>
#include <aws/io/socket_channel_handler.h>
#include <aws/io/tls_channel_handler.h>

#include <aws/common/condition_variable.h>
#include <aws/common/mutex.h>
#include <aws/common/string.h>
#include <aws/common/thread.h>

#include <string.h>

static void s_ws_handshake_transform(
    struct aws_http_message *request,
    void *user_data,
    aws_mqtt_transform_websocket_handshake_complete_fn *complete_fn,
    void *complete_ctx);

static const char *s_capsule_name_mqtt_client_connection = "aws_mqtt_client_connection";

/*******************************************************************************
 * New Connection
 ******************************************************************************/

struct mqtt_connection_binding {
    struct aws_mqtt_client_connection *native;

    /* Weak reference proxy to python self.
     * Lets us invoke callbacks on the python object without preventing the GC from cleaning it up. */
    PyObject *self_proxy;

    PyObject *on_connect;
    PyObject *on_any_publish;

    /* Dependencies that must outlive this */
    PyObject *client;
};

static void s_mqtt_python_connection_finish_destruction(struct mqtt_connection_binding *py_connection) {

    Py_DECREF(py_connection->self_proxy);
    Py_DECREF(py_connection->client);
    Py_XDECREF(py_connection->on_any_publish);

    aws_mem_release(aws_py_get_allocator(), py_connection);
}

static void s_start_destroy_native(struct mqtt_connection_binding *py_connection) {
    if (py_connection == NULL || py_connection->native == NULL) {
        return;
    }

    aws_mqtt_client_connection_release(py_connection->native);
}

static void s_mqtt_python_connection_termination(void *userdata) {

    if (userdata == NULL) {
        return; // The binding is dead - skip!
    }

    struct mqtt_connection_binding *py_connection = userdata;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    s_mqtt_python_connection_finish_destruction(py_connection);
    PyGILState_Release(state);
}

static void s_mqtt_python_connection_destructor_on_disconnect(
    struct aws_mqtt_client_connection *connection,
    void *user_data) {
    if (connection == NULL || user_data == NULL) {
        return; // The connection is dead - skip!
    }

    struct mqtt_connection_binding *py_connection = user_data;
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    s_start_destroy_native(py_connection);
    PyGILState_Release(state);
}

static void s_mqtt_python_connection_destructor(PyObject *connection_capsule) {

    struct mqtt_connection_binding *py_connection =
        PyCapsule_GetPointer(connection_capsule, s_capsule_name_mqtt_client_connection);
    AWS_FATAL_ASSERT(py_connection);
    AWS_FATAL_ASSERT(py_connection->native);

    /* This is the destructor from Python - so we can ignore the closed callback here */
    aws_mqtt_client_connection_set_connection_closed_handler(py_connection->native, NULL, NULL);

    if (aws_mqtt_client_connection_disconnect(
            py_connection->native, s_mqtt_python_connection_destructor_on_disconnect, py_connection)) {
        /* If we already disconnected, we should immediately release the native connection */
        s_start_destroy_native(py_connection);
    }
}

static void s_on_connection_success(
    struct aws_mqtt_client_connection *connection,
    enum aws_mqtt_connect_return_code return_code,
    bool session_present,
    void *user_data) {

    if (connection == NULL || user_data == NULL) {
        return; // The connection is dead - skip!
    }

    struct mqtt_connection_binding *py_connection = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *self = PyWeakref_GetObject(py_connection->self_proxy); /* borrowed reference */
    if (self != Py_None) {
        PyObject *success_result =
            PyObject_CallMethod(self, "_on_connection_success", "(iN)", return_code, PyBool_FromLong(session_present));
        if (success_result) {
            Py_DECREF(success_result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
    }

    PyGILState_Release(state);
}

static void s_on_connection_failure(struct aws_mqtt_client_connection *connection, int error_code, void *user_data) {

    if (connection == NULL || user_data == NULL) {
        return; // The connection is dead - skip!
    }

    struct mqtt_connection_binding *py_connection = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *self = PyWeakref_GetObject(py_connection->self_proxy); /* borrowed reference */
    if (self != Py_None) {
        PyObject *success_result = PyObject_CallMethod(self, "_on_connection_failure", "(i)", error_code);
        if (success_result) {
            Py_DECREF(success_result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
    }

    PyGILState_Release(state);
}

static void s_on_connection_interrupted(struct aws_mqtt_client_connection *connection, int error_code, void *userdata) {

    if (connection == NULL || userdata == NULL) {
        return; // The connection is dead - skip!
    }

    struct mqtt_connection_binding *py_connection = userdata;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Ensure that python class is still alive */
    PyObject *self = PyWeakref_GetObject(py_connection->self_proxy); /* borrowed reference */
    if (self != Py_None) {
        PyObject *result = PyObject_CallMethod(self, "_on_connection_interrupted", "(i)", error_code);
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
    }

    PyGILState_Release(state);
}

static void s_on_connection_resumed(
    struct aws_mqtt_client_connection *connection,
    enum aws_mqtt_connect_return_code return_code,
    bool session_present,
    void *userdata) {

    if (connection == NULL || userdata == NULL) {
        return; // The connection is dead - skip!
    }

    (void)connection;

    struct mqtt_connection_binding *py_connection = userdata;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Ensure that python class is still alive */
    PyObject *self = PyWeakref_GetObject(py_connection->self_proxy); /* borrowed reference */
    if (self != Py_None) {
        PyObject *result =
            PyObject_CallMethod(self, "_on_connection_resumed", "(iN)", return_code, PyBool_FromLong(session_present));
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
    }

    PyGILState_Release(state);
}

static void s_on_connection_closed(
    struct aws_mqtt_client_connection *connection,
    struct on_connection_closed_data *data,
    void *userdata) {

    if (connection == NULL || userdata == NULL) {
        return; // The connection is dead - skip!
    }
    (void)data; // Not used for anything currently, but in the future it could be.

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    struct mqtt_connection_binding *py_connection = userdata;
    /* Ensure that python class is still alive */
    PyObject *self = PyWeakref_GetObject(py_connection->self_proxy); /* borrowed reference */
    if (self != Py_None) {
        PyObject *result = PyObject_CallMethod(self, "_on_connection_closed", "()");
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
    }

    PyGILState_Release(state);
}

PyObject *aws_py_mqtt_client_connection_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *self_py;
    PyObject *client_py;
    PyObject *use_websocket_py;
    unsigned char client_version;
    if (!PyArg_ParseTuple(args, "OOOb", &self_py, &client_py, &use_websocket_py, &client_version)) {
        return NULL;
    }

    void *client = NULL;
    if (client_version == 3) {
        client = aws_py_get_mqtt_client(client_py);
    } else if (client_version == 5) {
        client = aws_py_get_mqtt5_client(client_py);
    } else {
        PyErr_SetString(PyExc_TypeError, "Mqtt Client version not supported. Failed to create connection.");
        return NULL;
    }

    if (!client) {
        return NULL;
    }

    struct mqtt_connection_binding *py_connection =
        aws_mem_calloc(allocator, 1, sizeof(struct mqtt_connection_binding));
    if (!py_connection) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */
    PyObject *self_proxy = NULL;

    if (client_version == 3) {
        py_connection->native = aws_mqtt_client_connection_new(client);
    } else if (client_version == 5) {
        py_connection->native = aws_mqtt_client_connection_new_from_mqtt5_client(client);
    }
    if (!py_connection->native) {
        PyErr_SetAwsLastError();
        goto on_error;
    }

    if (aws_mqtt_client_connection_set_connection_termination_handler(
            py_connection->native, s_mqtt_python_connection_termination, py_connection)) {
        PyErr_SetAwsLastError();
        goto on_error;
    }

    if (aws_mqtt_client_connection_set_connection_result_handlers(
            py_connection->native, s_on_connection_success, py_connection, s_on_connection_failure, py_connection)) {
        PyErr_SetAwsLastError();
        goto on_error;
    }

    if (aws_mqtt_client_connection_set_connection_interruption_handlers(
            py_connection->native,
            s_on_connection_interrupted,
            py_connection,
            s_on_connection_resumed,
            py_connection)) {

        PyErr_SetAwsLastError();
        goto on_error;
    }

    if (aws_mqtt_client_connection_set_connection_closed_handler(
            py_connection->native, s_on_connection_closed, py_connection)) {
        PyErr_SetAwsLastError();
        goto on_error;
    }

    if (PyObject_IsTrue(use_websocket_py)) {
        if (aws_mqtt_client_connection_use_websockets(
                py_connection->native,
                s_ws_handshake_transform,
                py_connection /*transform userdata*/,
                NULL /*validator*/,
                NULL /*validator userdata*/)) {

            PyErr_SetAwsLastError();
            goto on_error;
        }
    }

    self_proxy = PyWeakref_NewProxy(self_py, NULL);
    if (!self_proxy) {
        goto on_error;
    }

    PyObject *capsule =
        PyCapsule_New(py_connection, s_capsule_name_mqtt_client_connection, s_mqtt_python_connection_destructor);
    if (!capsule) {
        goto on_error;
    }

    /* From hereon, nothing will fail */
    py_connection->self_proxy = self_proxy;

    py_connection->client = client_py;
    Py_INCREF(py_connection->client);

    return capsule;

on_error:
    Py_XDECREF(self_proxy);
    aws_mqtt_client_connection_release(py_connection->native);
    aws_mem_release(allocator, py_connection);
    return NULL;
}

struct aws_mqtt_client_connection *aws_py_get_mqtt_client_connection(PyObject *mqtt_connection) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        mqtt_connection, s_capsule_name_mqtt_client_connection, "Connection", mqtt_connection_binding);
}

/*******************************************************************************
 * Connect
 ******************************************************************************/

static void s_on_connect(
    struct aws_mqtt_client_connection *connection,
    int error_code,
    enum aws_mqtt_connect_return_code return_code,
    bool session_present,
    void *user_data) {

    if (connection == NULL || user_data == NULL) {
        return; // The connection is dead - skip!
    }

    struct mqtt_connection_binding *py_connection = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    if (py_connection->on_connect) {

        PyObject *callback = py_connection->on_connect;
        py_connection->on_connect = NULL;

        PyObject *result =
            PyObject_CallFunction(callback, "(iiN)", error_code, return_code, PyBool_FromLong(session_present));
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }

        Py_XDECREF(callback);
    }

    PyGILState_Release(state);
}

/* If unsuccessful, false is returned and a Python error has been set */
bool s_set_will(struct aws_mqtt_client_connection *connection, PyObject *will) {
    assert(will && (will != Py_None));

    if (connection == NULL) {
        return false; // The connection is dead - skip!
    }

    bool success = false;

    /* These references all need to be cleaned up before function returns */
    PyObject *py_topic = NULL;
    PyObject *py_payload = NULL;

    py_topic = PyObject_GetAttrString(will, "topic");
    struct aws_byte_cursor topic = aws_byte_cursor_from_pyunicode(py_topic);
    if (!topic.ptr) {
        PyErr_SetString(PyExc_TypeError, "Will.topic must be str type");
        goto done;
    }

    enum aws_mqtt_qos qos = PyObject_GetAttrAsIntEnum(will, "Will", "qos");
    if (PyErr_Occurred()) {
        goto done;
    }

    py_payload = PyObject_GetAttrString(will, "payload");
    struct aws_byte_cursor payload = aws_byte_cursor_from_pybytes(py_payload);
    if (!payload.ptr) {
        PyErr_SetString(PyExc_TypeError, "Will.payload must be bytes type");
        goto done;
    }

    bool retain = PyObject_GetAttrAsBool(will, "Will", "retain");
    if (PyErr_Occurred()) {
        goto done;
    }

    if (aws_mqtt_client_connection_set_will(connection, &topic, qos, retain, &payload)) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;

done:
    Py_XDECREF(py_topic);
    Py_XDECREF(py_payload);
    return success;
}

/* Data to live for duration of websocket handshake transform callback.
 * Implementations can be async, but must call the complete_fn when they are done */
struct ws_handshake_transform_data {
    struct aws_http_message *request;
    aws_mqtt_transform_websocket_handshake_complete_fn *complete_fn;
    void *complete_ctx;

    /* Strong reference to Connection object, so it can't go out of scope during transform */
    PyObject *connection_py;

    /* Python bindings we created to wrap the native request */
    PyObject *request_binding_py;
    PyObject *headers_binding_py;
};

static const char *s_capsule_name_ws_handshake_transform_data = "aws_ws_handshake_transform_data";

void s_ws_handshake_transform_data_destructor(PyObject *capsule) {
    struct ws_handshake_transform_data *ws_data =
        PyCapsule_GetPointer(capsule, s_capsule_name_ws_handshake_transform_data);

    /* Note that binding may be only partially constructed, if error occurred during setup */
    Py_XDECREF(ws_data->connection_py);
    Py_XDECREF(ws_data->request_binding_py);
    Py_XDECREF(ws_data->headers_binding_py);

    aws_mem_release(aws_py_get_allocator(), ws_data);
}

/* Invoke user's websocket handshake transform function */
static void s_ws_handshake_transform(
    struct aws_http_message *request,
    void *user_data,
    aws_mqtt_transform_websocket_handshake_complete_fn *complete_fn,
    void *complete_ctx) {

    struct mqtt_connection_binding *connection_binding = user_data;

    bool success = false;

    /* We'll create a ws_handshake_transform_data object, place it in a capsule, and pass it to callback */
    struct ws_handshake_transform_data *ws_transform_data = NULL;
    PyObject *ws_transform_capsule = NULL;

    /*************** GIL ACQUIRE ***************
     * If error occurs, ensure an aws error is raised and goto done */
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Ensure python mqtt connection object is still alive */
    PyObject *connection_py = PyWeakref_GetObject(connection_binding->self_proxy); /* borrowed reference */
    if (connection_py == Py_None) {
        aws_raise_error(AWS_ERROR_INVALID_STATE);
        goto done;
    }

    ws_transform_data = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct ws_handshake_transform_data));
    if (!ws_transform_data) {
        goto done;
    }

    ws_transform_capsule = PyCapsule_New(
        ws_transform_data, s_capsule_name_ws_handshake_transform_data, s_ws_handshake_transform_data_destructor);
    if (!ws_transform_capsule) {
        aws_py_raise_error();
        goto done;
    }

    /* From hereon, capsule destructor will clean up anything stored within it */

    ws_transform_data->request = request;
    ws_transform_data->complete_fn = complete_fn;
    ws_transform_data->complete_ctx = complete_ctx;

    ws_transform_data->connection_py = connection_py;
    Py_INCREF(ws_transform_data->connection_py);

    ws_transform_data->request_binding_py = aws_py_http_message_new_request_from_native(request);
    if (!ws_transform_data->request_binding_py) {
        aws_py_raise_error();
        goto done;
    }

    ws_transform_data->headers_binding_py = aws_py_http_headers_new_from_native(aws_http_message_get_headers(request));
    if (!ws_transform_data->headers_binding_py) {
        aws_py_raise_error();
        goto done;
    }

    PyObject *result = PyObject_CallMethod(
        connection_py,
        "_ws_handshake_transform",
        "(OOO)",
        ws_transform_data->request_binding_py,
        ws_transform_data->headers_binding_py,
        ws_transform_capsule);

    if (result) {
        Py_DECREF(result);
    } else {
        aws_py_raise_error();
        goto done;
    }

    success = true;
done:;
    /* Save off error code, so it doesn't got stomped before we pass it to callback*/
    int error_code = aws_last_error();

    if (ws_transform_capsule) {
        Py_DECREF(ws_transform_capsule);
    } else if (ws_transform_data) {
        aws_mem_release(aws_py_get_allocator(), ws_transform_data);
    }

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    /* Invoke completion cb if we failed to pass data to user. */
    if (!success) {
        complete_fn(request, error_code, complete_ctx);
    }
}

/* Called when user finishes performing their websocket handshake transform */
PyObject *aws_py_mqtt_ws_handshake_transform_complete(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *exception_py;
    PyObject *ws_transform_capsule;
    int error_code = AWS_ERROR_SUCCESS;
    if (!PyArg_ParseTuple(args, "OOi", &exception_py, &ws_transform_capsule, &error_code)) {
        return NULL;
    }

    if (exception_py != Py_None && error_code == AWS_ERROR_SUCCESS) {
        /* Fallback code for if the error source was outside the CRT native implementation */
        error_code = AWS_ERROR_HTTP_CALLBACK_FAILURE;
    }

    struct ws_handshake_transform_data *ws_transform_data =
        PyCapsule_GetPointer(ws_transform_capsule, s_capsule_name_ws_handshake_transform_data);
    if (!ws_transform_data) {
        return NULL;
    }

    /* Invoke complete_fn*/
    ws_transform_data->complete_fn(ws_transform_data->request, error_code, ws_transform_data->complete_ctx);

    Py_RETURN_NONE;
}

PyObject *aws_py_mqtt_client_connection_connect(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    const char *client_id;
    Py_ssize_t client_id_len;
    const char *server_name;
    Py_ssize_t server_name_len;
    uint32_t port_number;
    PyObject *socket_options_py;
    PyObject *tls_ctx_py;
    uint64_t reconnect_min_timeout_secs;
    uint64_t reconnect_max_timeout_secs;
    uint16_t keep_alive_time;
    uint32_t ping_timeout;
    uint32_t protocol_operation_timeout;
    PyObject *will;
    const char *username;
    Py_ssize_t username_len;
    const char *password;
    Py_ssize_t password_len;
    PyObject *is_clean_session;
    PyObject *on_connect;
    PyObject *proxy_options_py;
    if (!PyArg_ParseTuple(
            args,
            "Os#s#IOOKKHIIOz#z#OOO",
            &impl_capsule,
            &client_id,
            &client_id_len,
            &server_name,
            &server_name_len,
            &port_number,
            &socket_options_py,
            &tls_ctx_py,
            &reconnect_min_timeout_secs,
            &reconnect_max_timeout_secs,
            &keep_alive_time,
            &ping_timeout,
            &protocol_operation_timeout,
            &will,
            &username,
            &username_len,
            &password,
            &password_len,
            &is_clean_session,
            &on_connect,
            &proxy_options_py)) {
        return NULL;
    }

    struct mqtt_connection_binding *py_connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!py_connection) {
        return NULL;
    }

    if (py_connection->on_connect) {
        PyErr_SetString(PyExc_RuntimeError, "Connection already in progress");
        return NULL;
    }

    struct aws_socket_options socket_options;
    if (!aws_py_socket_options_init(&socket_options, socket_options_py)) {
        return NULL;
    }

    struct aws_byte_cursor server_name_cur = aws_byte_cursor_from_array(server_name, server_name_len);

    if (aws_mqtt_client_connection_set_reconnect_timeout(
            py_connection->native, reconnect_min_timeout_secs, reconnect_max_timeout_secs)) {
        return PyErr_AwsLastError();
    }

    if (will != Py_None) {
        if (!s_set_will(py_connection->native, will)) {
            return NULL;
        }
    }

    if (username) {
        struct aws_byte_cursor username_cur = aws_byte_cursor_from_array(username, username_len);

        struct aws_byte_cursor password_cur;
        struct aws_byte_cursor *password_cur_ptr = NULL;
        if (password) {
            password_cur.ptr = (uint8_t *)password;
            password_cur.len = password_len;
            password_cur_ptr = &password_cur;
        }

        if (aws_mqtt_client_connection_set_login(py_connection->native, &username_cur, password_cur_ptr)) {
            return PyErr_AwsLastError();
        }
    }

    if (proxy_options_py != Py_None) {
        struct aws_http_proxy_options proxy_options;
        if (!aws_py_http_proxy_options_init(&proxy_options, proxy_options_py)) {
            return NULL;
        }

        if (aws_mqtt_client_connection_set_http_proxy_options(py_connection->native, &proxy_options)) {
            return PyErr_AwsLastError();
        }
    }

    struct aws_tls_ctx *tls_ctx = NULL;
    struct aws_tls_connection_options tls_options;
    AWS_ZERO_STRUCT(tls_options);

    /* From hereon, we need to clean up if errors occur */
    bool success = false;

    if (tls_ctx_py != Py_None) {
        tls_ctx = aws_py_get_tls_ctx(tls_ctx_py);
        if (!tls_ctx) {
            goto done;
        }

        aws_tls_connection_options_init_from_ctx(&tls_options, tls_ctx);
        struct aws_allocator *allocator = aws_py_get_allocator();
        struct aws_byte_cursor server_name_cur = aws_byte_cursor_from_c_str(server_name);
        if (aws_tls_connection_options_set_server_name(&tls_options, allocator, &server_name_cur)) {
            PyErr_SetAwsLastError();
            goto done;
        }
    }

    if (on_connect != Py_None) {
        Py_INCREF(on_connect);
        py_connection->on_connect = on_connect;
    }

    struct aws_byte_cursor client_id_cur = aws_byte_cursor_from_array(client_id, client_id_len);
    struct aws_mqtt_connection_options options = {
        .host_name = server_name_cur,
        .port = port_number,
        .socket_options = &socket_options,
        .tls_options = tls_ctx ? &tls_options : NULL,
        .client_id = client_id_cur,
        .keep_alive_time_secs = keep_alive_time,
        .ping_timeout_ms = ping_timeout,
        .protocol_operation_timeout_ms = protocol_operation_timeout,
        .on_connection_complete = s_on_connect,
        .user_data = py_connection,
        .clean_session = PyObject_IsTrue(is_clean_session),
    };
    if (aws_mqtt_client_connection_connect(py_connection->native, &options)) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;
done:
    aws_tls_connection_options_clean_up(&tls_options);
    if (success) {
        Py_RETURN_NONE;
    }

    Py_CLEAR(py_connection->on_connect);
    return NULL;
}

/*******************************************************************************
 * Reconnect
 ******************************************************************************/

PyObject *aws_py_mqtt_client_connection_reconnect(PyObject *self, PyObject *args) {

    (void)self;

    PyObject *impl_capsule;
    PyObject *on_connect;
    if (!PyArg_ParseTuple(args, "OO", &impl_capsule, &on_connect)) {
        return NULL;
    }

    struct mqtt_connection_binding *py_connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!py_connection) {
        return NULL;
    }

    if (py_connection->on_connect) {
        PyErr_SetString(PyExc_RuntimeError, "Connection already in progress");
        return NULL;
    }

    if (on_connect != Py_None) {
        Py_INCREF(on_connect);
        py_connection->on_connect = on_connect;
    }

    if (aws_mqtt_client_connection_reconnect(py_connection->native, s_on_connect, py_connection)) {
        Py_CLEAR(py_connection->on_connect);
        PyErr_SetAwsLastError();
        return NULL;
    }

    Py_RETURN_NONE;
}

/*******************************************************************************
 * Publish
 ******************************************************************************/

struct publish_complete_userdata {
    PyObject *callback;
};

static void s_publish_complete(
    struct aws_mqtt_client_connection *connection,
    uint16_t packet_id,
    int error_code,
    void *userdata) {

    if (connection == NULL || userdata == NULL) {
        return; // The connection is dead - skip!
    }

    struct publish_complete_userdata *metadata = userdata;
    assert(metadata);

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    if (metadata->callback != Py_None) {
        PyObject *result = PyObject_CallFunction(metadata->callback, "(Hi)", packet_id, error_code);
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
    }

    Py_DECREF(metadata->callback);

    PyGILState_Release(state);

    aws_mem_release(aws_py_get_allocator(), metadata);
}

PyObject *aws_py_mqtt_client_connection_publish(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    Py_buffer topic_stack; /* Py_buffers must be released after successful PyArg_ParseTuple() calls */
    Py_buffer payload_stack;
    uint8_t qos_val;
    PyObject *retain;
    PyObject *puback_callback;
    if (!PyArg_ParseTuple(
            args, "Os*s*bOO", &impl_capsule, &topic_stack, &payload_stack, &qos_val, &retain, &puback_callback)) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    struct mqtt_connection_binding *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!connection) {
        goto arg_error;
    }

    if (qos_val >= AWS_MQTT_QOS_EXACTLY_ONCE) {
        PyErr_SetNone(PyExc_ValueError);
        goto arg_error;
    }

    struct publish_complete_userdata *metadata = NULL;

    /* Heap allocate payload so that it may persist */
    metadata = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct publish_complete_userdata));
    if (!metadata) {
        PyErr_SetAwsLastError();
        goto metadata_alloc_failed;
    }

    metadata->callback = puback_callback;
    Py_INCREF(metadata->callback);

    struct aws_byte_cursor topic_cursor;
    topic_cursor = aws_byte_cursor_from_array(topic_stack.buf, topic_stack.len);

    struct aws_byte_cursor payload_cursor;
    payload_cursor = aws_byte_cursor_from_array(payload_stack.buf, payload_stack.len);

    enum aws_mqtt_qos qos = (enum aws_mqtt_qos)qos_val;

    uint16_t msg_id = aws_mqtt_client_connection_publish(
        connection->native, &topic_cursor, qos, retain == Py_True, &payload_cursor, s_publish_complete, metadata);

    if (msg_id == 0) {
        PyErr_SetAwsLastError();
        goto publish_failed;
    }
    PyBuffer_Release(&topic_stack);
    PyBuffer_Release(&payload_stack);

    return PyLong_FromUnsignedLong(msg_id);

publish_failed:
    Py_DECREF(metadata->callback);
    aws_mem_release(aws_py_get_allocator(), metadata);
metadata_alloc_failed:
arg_error:
    PyBuffer_Release(&topic_stack);
    PyBuffer_Release(&payload_stack);
    return NULL;
}

/*******************************************************************************
 * Subscribe
 ******************************************************************************/

static void s_subscribe_callback(
    struct aws_mqtt_client_connection *connection,
    const struct aws_byte_cursor *topic,
    const struct aws_byte_cursor *payload,
    bool dup,
    enum aws_mqtt_qos qos,
    bool retain,
    void *user_data) {

    if (connection == NULL || user_data == NULL) {
        return; // The connection is dead - skip!
    }

    PyObject *callback = user_data;
    if (callback == Py_None) {
        return;
    }

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallFunction(
        callback,
        "(s#y#OiO)",
        topic->ptr,
        topic->len,
        payload->ptr,
        payload->len,
        dup ? Py_True : Py_False,
        qos,
        retain ? Py_True : Py_False);

    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    PyGILState_Release(state);
}

static void s_callback_cleanup(void *userdata) {
    PyObject *callback = userdata;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    Py_DECREF(callback);

    PyGILState_Release(state);
}

static void s_suback_callback(
    struct aws_mqtt_client_connection *connection,
    uint16_t packet_id,
    const struct aws_byte_cursor *topic,
    enum aws_mqtt_qos qos,
    int error_code,
    void *userdata) {

    if (connection == NULL || userdata == NULL) {
        return; // The connection is dead - skip!
    }

    PyObject *callback = userdata;
    AWS_FATAL_ASSERT(callback && callback != Py_None);

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    const char *topic_str = (const char *)topic->ptr;
    Py_ssize_t topic_len = topic->len;
    PyObject *result = PyObject_CallFunction(callback, "(Hs#Bi)", packet_id, topic_str, topic_len, qos, error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    Py_DECREF(callback);

    PyGILState_Release(state);
}

PyObject *aws_py_mqtt_client_connection_subscribe(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    const char *topic;
    Py_ssize_t topic_len;
    uint8_t qos_val;
    PyObject *callback;
    PyObject *suback_callback;
    if (!PyArg_ParseTuple(args, "Os#bOO", &impl_capsule, &topic, &topic_len, &qos_val, &callback, &suback_callback)) {
        return NULL;
    }

    struct mqtt_connection_binding *py_connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!py_connection) {
        return NULL;
    }

    Py_INCREF(callback);
    Py_INCREF(suback_callback);

    struct aws_byte_cursor topic_filter = aws_byte_cursor_from_array(topic, topic_len);
    uint16_t msg_id = aws_mqtt_client_connection_subscribe(
        py_connection->native,
        &topic_filter,
        qos_val,
        s_subscribe_callback,
        callback,
        s_callback_cleanup,
        s_suback_callback,
        suback_callback);

    if (msg_id == 0) {
        Py_DECREF(callback);
        Py_DECREF(suback_callback);
        return PyErr_AwsLastError();
    }

    return PyLong_FromUnsignedLong(msg_id);
}

PyObject *aws_py_mqtt_client_connection_on_message(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    PyObject *callback;
    if (!PyArg_ParseTuple(args, "OO", &impl_capsule, &callback)) {
        return NULL;
    }

    struct mqtt_connection_binding *py_connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!py_connection) {
        return NULL;
    }

    if (callback == Py_None) {
        if (aws_mqtt_client_connection_set_on_any_publish_handler(py_connection->native, NULL, NULL)) {
            return PyErr_AwsLastError();
        }
    } else {
        if (aws_mqtt_client_connection_set_on_any_publish_handler(
                py_connection->native, s_subscribe_callback, callback)) {
            return PyErr_AwsLastError();
        }
    }

    Py_XDECREF(py_connection->on_any_publish);

    py_connection->on_any_publish = callback;
    Py_INCREF(callback);

    Py_RETURN_NONE;
}

/*******************************************************************************
 * Unsubscribe
 ******************************************************************************/

static void s_unsuback_callback(
    struct aws_mqtt_client_connection *connection,
    uint16_t packet_id,
    int error_code,
    void *userdata) {

    if (connection == NULL || userdata == NULL) {
        return; // The connection is dead - skip!
    }

    PyObject *callback = userdata;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallFunction(callback, "(Hi)", packet_id, error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    Py_DECREF(callback);

    PyGILState_Release(state);
}

PyObject *aws_py_mqtt_client_connection_unsubscribe(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    const char *topic;
    Py_ssize_t topic_len;
    PyObject *unsuback_callback;
    if (!PyArg_ParseTuple(args, "Os#O", &impl_capsule, &topic, &topic_len, &unsuback_callback)) {
        return NULL;
    }

    struct mqtt_connection_binding *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!connection) {
        return NULL;
    }

    struct aws_byte_cursor filter = aws_byte_cursor_from_array(topic, topic_len);
    Py_INCREF(unsuback_callback);
    uint16_t msg_id =
        aws_mqtt_client_connection_unsubscribe(connection->native, &filter, s_unsuback_callback, unsuback_callback);

    if (msg_id == 0) {
        Py_DECREF(unsuback_callback);
        return PyErr_AwsLastError();
    }

    return PyLong_FromUnsignedLong(msg_id);
}

/*******************************************************************************
 * Resubscribe
 ******************************************************************************/

static void s_suback_multi_callback(
    struct aws_mqtt_client_connection *connection,
    uint16_t packet_id,
    const struct aws_array_list *topic_subacks, /* contains aws_mqtt_topic_subscription pointers */
    int error_code,
    void *userdata) {

    if (connection == NULL || userdata == NULL) {
        return; // The connection is dead - skip!
    }

    /* These must be DECREF'd when function ends */
    PyObject *callback = userdata;
    PyObject *callback_result = NULL;
    PyObject *topic_qos_list = NULL;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    if (error_code) {
        goto done_prepping_args;
    }

    const size_t num_topics = aws_array_list_length(topic_subacks);

    /* Create list of (topic,qos) tuples */
    topic_qos_list = PyList_New(num_topics);
    if (!topic_qos_list) {
        error_code = aws_py_translate_py_error();
        goto done_prepping_args;
    }

    for (size_t i = 0; i < num_topics; ++i) {
        struct aws_mqtt_topic_subscription *sub_i = NULL;
        aws_array_list_get_at(topic_subacks, &sub_i, i);
        PyObject *tuple = Py_BuildValue("(s#i)", sub_i->topic.ptr, sub_i->topic.len, sub_i->qos);
        if (!tuple) {
            error_code = aws_py_translate_py_error();
            goto done_prepping_args;
        }

        PyList_SetItem(topic_qos_list, i, tuple); /* Steals reference to tuple */
    }

done_prepping_args:;

    /* Don't pass the list if there was an error, since the list might be only partially constructed */
    callback_result =
        PyObject_CallFunction(callback, "(HOi)", packet_id, (error_code ? Py_None : topic_qos_list), error_code);
    if (!callback_result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    Py_DECREF(callback);
    Py_XDECREF(callback_result);
    Py_XDECREF(topic_qos_list);
    PyGILState_Release(state);
}

PyObject *aws_py_mqtt_client_connection_resubscribe_existing_topics(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    PyObject *suback_callback;
    if (!PyArg_ParseTuple(args, "OO", &impl_capsule, &suback_callback)) {
        return NULL;
    }

    struct mqtt_connection_binding *py_connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!py_connection) {
        return NULL;
    }

    if (!PyCallable_Check(suback_callback)) {
        PyErr_SetString(PyExc_TypeError, "suback_callback is not callable");
        return NULL;
    }

    Py_INCREF(suback_callback);
    uint16_t msg_id =
        aws_mqtt_resubscribe_existing_topics(py_connection->native, s_suback_multi_callback, suback_callback);
    if (msg_id == 0) {
        /* C will not be invoking the python callback */
        Py_DECREF(suback_callback);

        int aws_err = aws_last_error();
        if (aws_err) {
            PyErr_SetAwsLastError();
            return NULL;
        }
    }

    return PyLong_FromUnsignedLong(msg_id);
}

/*******************************************************************************
 * Disconnect
 ******************************************************************************/

static void s_on_disconnect(struct aws_mqtt_client_connection *connection, void *user_data) {

    if (connection == NULL || user_data == NULL) {
        return; // The connection is dead - skip!
    }

    PyObject *on_disconnect = user_data;

    if (on_disconnect) {
        PyGILState_STATE state;
        if (aws_py_gilstate_ensure(&state)) {
            return; /* Python has shut down. Nothing matters anymore, but don't crash */
        }

        PyObject *result = PyObject_CallFunction(on_disconnect, "()");
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }

        Py_DECREF(on_disconnect);

        PyGILState_Release(state);
    }
}

PyObject *aws_py_mqtt_client_connection_disconnect(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    PyObject *on_disconnect;
    if (!PyArg_ParseTuple(args, "OO", &impl_capsule, &on_disconnect)) {
        return NULL;
    }

    struct mqtt_connection_binding *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!connection) {
        return NULL;
    }

    Py_INCREF(on_disconnect);

    int err = aws_mqtt_client_connection_disconnect(connection->native, s_on_disconnect, on_disconnect);
    if (err) {
        Py_DECREF(on_disconnect);
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

/*******************************************************************************
 * Client Statistics
 ******************************************************************************/

PyObject *aws_py_mqtt_client_connection_get_stats(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *impl_capsule;

    if (!PyArg_ParseTuple(args, "O", &impl_capsule)) {
        return NULL;
    }

    struct mqtt_connection_binding *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!connection) {
        return NULL;
    }

    /* These must be DECREF'd when function ends on error */
    PyObject *result = NULL;

    struct aws_mqtt_connection_operation_statistics stats;
    AWS_ZERO_STRUCT(stats);

    aws_mqtt_client_connection_get_stats(connection->native, &stats);

    result = PyTuple_New(4);
    if (!result) {
        goto done;
    }

    PyTuple_SetItem(
        result,
        0,
        PyLong_FromUnsignedLongLong((unsigned long long)stats.incomplete_operation_count)); /* Steals a reference */
    if (PyTuple_GetItem(result, 0) == NULL) {                                               /* Borrowed reference */
        goto done;
    }

    PyTuple_SetItem(
        result,
        1,
        PyLong_FromUnsignedLongLong((unsigned long long)stats.incomplete_operation_size)); /* Steals a reference */
    if (PyTuple_GetItem(result, 1) == NULL) {                                              /* Borrowed reference */
        goto done;
    }

    PyTuple_SetItem(
        result,
        2,
        PyLong_FromUnsignedLongLong((unsigned long long)stats.unacked_operation_count)); /* Steals a reference */
    if (PyTuple_GetItem(result, 2) == NULL) {                                            /* Borrowed reference */
        goto done;
    }

    PyTuple_SetItem(
        result,
        3,
        PyLong_FromUnsignedLongLong((unsigned long long)stats.unacked_operation_size)); /* Steals a reference */
    if (PyTuple_GetItem(result, 3) == NULL) {                                           /* Borrowed reference */
        goto done;
    }

    success = true;

done:
    if (success) {
        return result;
    }
    Py_XDECREF(result);
    return NULL;
}
