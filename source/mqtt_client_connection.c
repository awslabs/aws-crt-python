/*
 * Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
#include "mqtt_client_connection.h"

#include "io.h"
#include "mqtt_client.h"

#include <aws/mqtt/client.h>

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

const char *s_capsule_name_mqtt_client_connection = "aws_mqtt_client_connection";

/*******************************************************************************
 * New Connection
 ******************************************************************************/

struct mqtt_python_connection {
    struct aws_socket_options socket_options;
    struct aws_tls_connection_options tls_options;
    struct mqtt_python_client *py_client;
    struct aws_mqtt_client_connection *connection;

    PyObject *on_connect;
    PyObject *on_disconnect;
};

static void s_mqtt_python_connection_destructor(PyObject *connection_capsule) {

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    assert(PyCapsule_CheckExact(connection_capsule));

    struct mqtt_python_connection *py_connection =
        PyCapsule_GetPointer(connection_capsule, s_capsule_name_mqtt_client_connection);
    assert(py_connection);

    Py_XDECREF(py_connection->on_connect);
    Py_XDECREF(py_connection->on_disconnect);

    aws_mqtt_client_connection_disconnect(py_connection->connection);

    aws_mem_release(allocator, py_connection);
}

static void s_on_connect_failed(struct aws_mqtt_client_connection *connection, int error_code, void *user_data) {

    (void)connection;

    struct mqtt_python_connection *py_connection = user_data;

    if (py_connection->on_disconnect) {
        PyGILState_STATE state = PyGILState_Ensure();

        PyObject *result = PyObject_CallFunction(py_connection->on_disconnect, "(I)", error_code);
        Py_XDECREF(result);

        PyGILState_Release(state);
    }
}

static void s_on_connect(
    struct aws_mqtt_client_connection *connection,
    enum aws_mqtt_connect_return_code return_code,
    bool session_present,
    void *user_data) {

    (void)connection;

    struct mqtt_python_connection *py_connection = user_data;

    if (py_connection->on_connect) {
        PyGILState_STATE state = PyGILState_Ensure();

        PyObject *result =
            PyObject_CallFunction(py_connection->on_connect, "(IN)", return_code, PyBool_FromLong(session_present));
        Py_XDECREF(result);

        PyGILState_Release(state);
    }
}

static bool s_on_disconnect(struct aws_mqtt_client_connection *connection, int error_code, void *user_data) {

    (void)connection;

    struct mqtt_python_connection *py_connection = user_data;

    bool should_reconnect = true;

    if (py_connection->on_disconnect) {
        PyGILState_STATE state = PyGILState_Ensure();

        PyObject *result = PyObject_CallFunction(py_connection->on_disconnect, "(I)", error_code);
        if (result) {
            if (result != Py_None) {
                should_reconnect = PyObject_IsTrue(result);
            }
            Py_DECREF(result);
        }

        PyGILState_Release(state);
    }

    return should_reconnect;
}

PyObject *aws_py_mqtt_client_connection_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    /* If anything goes wrong in this function: goto error */
    struct mqtt_python_connection *py_connection = NULL;
    struct aws_tls_ctx *tls_ctx = NULL;

    PyObject *client_capsule = NULL;
    PyObject *tls_ctx_capsule = NULL;
    const char *server_name = NULL;
    Py_ssize_t server_name_len = 0;
    uint16_t port_number = 0;
    const char *client_id = NULL;
    Py_ssize_t client_id_len = 0;
    uint16_t keep_alive_time = 0;
    PyObject *on_connect = NULL;
    PyObject *on_disconnect = NULL;
    PyObject *will = NULL;
    const char *username = NULL;
    Py_ssize_t username_len = 0;
    const char *password = NULL;
    Py_ssize_t password_len = 0;

    if (!PyArg_ParseTuple(
            args,
            "OOs#Hs#HOOOz#z#",
            &client_capsule,
            &tls_ctx_capsule,
            &server_name,
            &server_name_len,
            &port_number,
            &client_id,
            &client_id_len,
            &keep_alive_time,
            &on_connect,
            &on_disconnect,
            &will,
            &username,
            &username_len,
            &password,
            &password_len)) {
        goto error;
    }

    py_connection = aws_mem_acquire(allocator, sizeof(struct mqtt_python_connection));
    if (!py_connection) {
        PyErr_SetAwsLastError();
        goto error;
    }
    AWS_ZERO_STRUCT(*py_connection);

    if (!client_capsule || !PyCapsule_CheckExact(client_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }
    py_connection->py_client = PyCapsule_GetPointer(client_capsule, s_capsule_name_mqtt_client);
    if (!py_connection->py_client) {
        goto error;
    }

    if (tls_ctx_capsule != Py_None && PyCapsule_CheckExact(tls_ctx_capsule)) {
        tls_ctx = PyCapsule_GetPointer(tls_ctx_capsule, s_capsule_name_tls_ctx);
        if (!tls_ctx) {
            goto error;
        }
    }

    if (on_connect && PyCallable_Check(on_connect)) {
        Py_INCREF(on_connect);
        py_connection->on_connect = on_connect;
    }

    if (on_disconnect && PyCallable_Check(on_disconnect)) {
        Py_INCREF(on_disconnect);
        py_connection->on_disconnect = on_disconnect;
    }

    if (tls_ctx) {
        aws_tls_connection_options_init_from_ctx(&py_connection->tls_options, tls_ctx);
        aws_tls_connection_options_set_server_name(&py_connection->tls_options, server_name);
    }

    AWS_ZERO_STRUCT(py_connection->socket_options);
    py_connection->socket_options.connect_timeout_ms = 3000;
    py_connection->socket_options.type = AWS_SOCKET_STREAM;
    py_connection->socket_options.domain = AWS_SOCKET_IPV4;

    struct aws_mqtt_client_connection_callbacks callbacks;
    AWS_ZERO_STRUCT(callbacks);
    callbacks.on_connection_failed = s_on_connect_failed;
    callbacks.on_connack = s_on_connect;
    callbacks.on_disconnect = s_on_disconnect;
    callbacks.user_data = py_connection;

    struct aws_byte_cursor server_name_cur = aws_byte_cursor_from_array(server_name, server_name_len);

    py_connection->connection = aws_mqtt_client_connection_new(
        &py_connection->py_client->native_client,
        callbacks,
        &server_name_cur,
        port_number,
        &py_connection->socket_options,
        tls_ctx ? &py_connection->tls_options : NULL);

    if (!py_connection->connection) {
        PyErr_SetAwsLastError();
        goto error;
    }

    if (will && will != Py_None) {
        PyObject *py_topic = PyObject_GetAttrString(will, "topic");
        assert(py_topic);
        struct aws_byte_cursor topic = aws_byte_cursor_from_pystring(py_topic);

        PyObject *py_qos = PyObject_GetAttrString(will, "qos");
        assert(py_qos && PyLong_Check(py_qos));
        enum aws_mqtt_qos qos = (enum aws_mqtt_qos)PyLong_AsUnsignedLong(py_qos);

        PyObject *py_payload = PyObject_GetAttrString(will, "payload");
        assert(py_payload);
        struct aws_byte_cursor payload = aws_byte_cursor_from_pystring(py_payload);

        PyObject *py_retain = PyObject_GetAttrString(will, "retain");
        assert(py_retain && PyBool_Check(py_retain));
        bool retain = py_retain == Py_True;

        aws_mqtt_client_connection_set_will(py_connection->connection, &topic, qos, retain, &payload);
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

        aws_mqtt_client_connection_set_login(py_connection->connection, &username_cur, password_cur_ptr);
    }

    struct aws_byte_cursor client_id_cur = aws_byte_cursor_from_array(client_id, client_id_len);
    if (aws_mqtt_client_connection_connect(py_connection->connection, &client_id_cur, true, keep_alive_time)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return PyCapsule_New(py_connection, s_capsule_name_mqtt_client_connection, s_mqtt_python_connection_destructor);

error:
    if (py_connection) {
        if (py_connection->connection) {
            aws_mem_release(allocator, py_connection->connection); /* TODO: need aws_mqtt_client_connection_destroy() */
        }

        aws_mem_release(allocator, py_connection);
    }

    return NULL;
}

/*******************************************************************************
 * Publish
 ******************************************************************************/

struct publish_complete_userdata {
    Py_buffer payload;
    PyObject *callback;
};

static void s_publish_complete(
    struct aws_mqtt_client_connection *connection,
    uint16_t packet_id,
    int error_code,
    void *userdata) {
    (void)connection;
    (void)error_code;

    struct publish_complete_userdata *metadata = userdata;
    if (metadata) {

        PyGILState_STATE state = PyGILState_Ensure();

        if (metadata->callback) {

            PyObject_CallFunction(metadata->callback, "(H)", packet_id);
            Py_DECREF(metadata->callback);
        }
        PyBuffer_Release(&metadata->payload);

        PyGILState_Release(state);

        aws_mem_release(aws_crt_python_get_allocator(), metadata);
    }
}

PyObject *aws_py_mqtt_client_connection_publish(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule = NULL;
    const char *topic;
    Py_ssize_t topic_len;
    Py_buffer payload_stack;
    AWS_ZERO_STRUCT(payload_stack);
    uint8_t qos_val = AWS_MQTT_QOS_AT_MOST_ONCE;
    PyObject *retain = NULL;
    PyObject *puback_callback = NULL;

    if (!PyArg_ParseTuple(
            args, "Os#s*bOO", &impl_capsule, &topic, &topic_len, &payload_stack, &qos_val, &retain, &puback_callback)) {
        return NULL;
    }

    if (!impl_capsule || !PyCapsule_CheckExact(impl_capsule)) {
        PyErr_SetNone(PyExc_TypeError);
        return NULL;
    }

    struct mqtt_python_connection *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);

    if (qos_val > 3) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }
    if (puback_callback && PyCallable_Check(puback_callback)) {
        Py_INCREF(puback_callback);
    } else {
        puback_callback = NULL;
    }

    struct publish_complete_userdata *metadata = NULL;

    struct aws_byte_cursor payload_cursor;
    AWS_ZERO_STRUCT(payload_cursor);

    /* Heap allocate payload so that it may persist */
    if (payload_stack.len > 0 || puback_callback) {
        metadata = aws_mem_acquire(aws_crt_python_get_allocator(), sizeof(struct publish_complete_userdata));
        if (!metadata) {
            return PyErr_AwsLastError();
        }

        memcpy(&metadata->payload, &payload_stack, sizeof(Py_buffer));
        metadata->callback = puback_callback;

        payload_cursor = aws_byte_cursor_from_array(metadata->payload.buf, metadata->payload.len);
    }

    struct aws_byte_cursor topic_cursor = aws_byte_cursor_from_array(topic, topic_len);
    enum aws_mqtt_qos qos = (enum aws_mqtt_qos)qos_val;

    uint16_t msg_id = aws_mqtt_client_connection_publish(
        connection->connection, &topic_cursor, qos, retain == Py_True, &payload_cursor, s_publish_complete, metadata);

    if (msg_id == 0) {
        return PyErr_AwsLastError();
    }

    return PyLong_FromUnsignedLong(msg_id);
}

/*******************************************************************************
 * Subscribe
 ******************************************************************************/

static void s_subscribe_callback(
    struct aws_mqtt_client_connection *connection,
    const struct aws_byte_cursor *topic,
    const struct aws_byte_cursor *payload,
    void *user_data) {

    (void)connection;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *callback = user_data;

    PyObject *result =
        PyObject_CallFunction(callback, "(NN)", PyString_FromAwsByteCursor(topic), PyString_FromAwsByteCursor(payload));

    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        abort();
    }
    Py_XDECREF(result);

    PyGILState_Release(state);
}

static void s_callback_cleanup(void *userdata) {
    PyObject *callback = userdata;

    PyGILState_STATE state = PyGILState_Ensure();

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

    (void)connection;
    (void)error_code;

    PyObject *callback = userdata;

    if (callback) {

        PyGILState_STATE state = PyGILState_Ensure();

        const char *topic_str = (const char *)topic->ptr;
        Py_ssize_t topic_len = topic->len;

        PyObject *result = PyObject_CallFunction(callback, "(Hs#L)", packet_id, topic_str, topic_len, qos);
        if (!result) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            abort();
        } else {
            Py_DECREF(callback);
        }

        PyGILState_Release(state);
    }
}

PyObject *aws_py_mqtt_client_connection_subscribe(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule = NULL;
    const char *topic = NULL;
    Py_ssize_t topic_len = 0;
    uint8_t qos_val = 0;
    PyObject *callback = NULL;
    PyObject *suback_callback = NULL;

    if (!PyArg_ParseTuple(args, "Os#bOO", &impl_capsule, &topic, &topic_len, &qos_val, &callback, &suback_callback)) {
        return NULL;
    }

    if (!impl_capsule || !PyCapsule_CheckExact(impl_capsule)) {
        PyErr_SetNone(PyExc_TypeError);
        return NULL;
    }

    if (!callback || !PyCallable_Check(callback)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }
    Py_INCREF(callback);

    if (suback_callback && PyCallable_Check(suback_callback)) {
        Py_INCREF(suback_callback);
    } else {
        suback_callback = NULL;
    }

    struct mqtt_python_connection *py_connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);

    if (qos_val > 3) {
        PyErr_SetNone(PyExc_ValueError);
    }

    struct aws_byte_cursor topic_filter = aws_byte_cursor_from_array(topic, topic_len);
    uint16_t msg_id = aws_mqtt_client_connection_subscribe(
        py_connection->connection,
        &topic_filter,
        qos_val,
        s_subscribe_callback,
        callback,
        s_callback_cleanup,
        s_suback_callback,
        suback_callback);

    if (msg_id == 0) {
        return PyErr_AwsLastError();
    }

    return PyLong_FromUnsignedLong(msg_id);
}

/*******************************************************************************
 * Unsubscribe
 ******************************************************************************/

static void s_unsuback_callback(
    struct aws_mqtt_client_connection *connection,
    uint16_t packet_id,
    int error_code,
    void *userdata) {
    (void)connection;
    (void)error_code;

    PyObject *callback = userdata;

    if (callback) {

        PyGILState_STATE state = PyGILState_Ensure();

        PyObject_CallFunction(callback, "(H)", packet_id);
        Py_DECREF(callback);

        PyGILState_Release(state);
    }
}

PyObject *aws_py_mqtt_client_connection_unsubscribe(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule = NULL;
    const char *topic = NULL;
    Py_ssize_t topic_len = 0;
    PyObject *unsuback_callback = NULL;

    if (!PyArg_ParseTuple(args, "Os#O", &impl_capsule, &topic, &topic_len, &unsuback_callback)) {
        return NULL;
    }

    if (!impl_capsule || !PyCapsule_CheckExact(impl_capsule)) {
        PyErr_SetNone(PyExc_TypeError);
        return NULL;
    }

    if (unsuback_callback && PyCallable_Check(unsuback_callback)) {
        Py_INCREF(unsuback_callback);
    } else {
        unsuback_callback = NULL;
    }

    struct mqtt_python_connection *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);

    struct aws_byte_cursor filter = aws_byte_cursor_from_array(topic, topic_len);
    uint16_t msg_id =
        aws_mqtt_client_connection_unsubscribe(connection->connection, &filter, s_unsuback_callback, unsuback_callback);

    if (msg_id == 0) {
        return PyErr_AwsLastError();
    }

    return PyLong_FromUnsignedLong(msg_id);
}

/*******************************************************************************
 * Ping
 ******************************************************************************/

PyObject *aws_py_mqtt_client_connection_ping(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule = NULL;

    if (!PyArg_ParseTuple(args, "O", &impl_capsule)) {
        return NULL;
    }

    if (!impl_capsule || !PyCapsule_CheckExact(impl_capsule)) {
        PyErr_SetNone(PyExc_TypeError);
        return NULL;
    }

    struct mqtt_python_connection *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);

    int err = aws_mqtt_client_connection_ping(connection->connection);
    if (err) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

/*******************************************************************************
 * Disconnect
 ******************************************************************************/

PyObject *aws_py_mqtt_client_connection_disconnect(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule = NULL;

    if (!PyArg_ParseTuple(args, "O", &impl_capsule)) {
        return NULL;
    }

    if (!impl_capsule || !PyCapsule_CheckExact(impl_capsule)) {
        PyErr_SetNone(PyExc_TypeError);
        return NULL;
    }

    struct mqtt_python_connection *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);

    int err = aws_mqtt_client_connection_disconnect(connection->connection);
    if (err) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}
