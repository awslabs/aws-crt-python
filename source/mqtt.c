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
#include "mqtt.h"
#include "io.h"

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
    struct aws_mqtt_client client;
    struct aws_mqtt_client_connection *connection;

    PyObject *on_connect;
    PyObject *on_disconnect;
};

static void s_mqtt_python_connection_destructor(PyObject *connection_capsule) {

    assert(PyCapsule_CheckExact(connection_capsule));

    struct mqtt_python_connection *connection =
        PyCapsule_GetPointer(connection_capsule, s_capsule_name_mqtt_client_connection);
    assert(connection);

    Py_XDECREF(connection->on_connect);
    Py_XDECREF(connection->on_disconnect);

    aws_mqtt_client_connection_disconnect(connection->connection);
    aws_mqtt_client_clean_up(&connection->client);

    aws_mem_release(aws_crt_python_get_allocator(), connection);
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

static void s_on_disconnect(struct aws_mqtt_client_connection *connection, int error_code, void *user_data) {

    (void)connection;

    struct mqtt_python_connection *py_connection = user_data;

    if (py_connection->on_disconnect) {
        PyGILState_STATE state = PyGILState_Ensure();

        PyObject *result = PyObject_CallFunction(py_connection->on_disconnect, "(I)", error_code);
        Py_XDECREF(result);

        PyGILState_Release(state);
    }
}

PyObject *mqtt_new_connection(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    PyObject *elg_capsule = NULL;
    const char *server_name = NULL;
    Py_ssize_t server_name_len = 0;
    uint16_t port_number = 0;
    const char *ca_path = NULL;
    const char *key_path = NULL;
    const char *cert_path = NULL;
    const char *alpn_protocol = NULL;
    const char *client_id = NULL;
    Py_ssize_t client_id_len = 0;
    uint16_t keep_alive_time = 0;
    PyObject *on_connect = NULL;
    PyObject *on_disconnect = NULL;

    if (!PyArg_ParseTuple(
            args,
            "Os#Hsszzs#HOO",
            &elg_capsule,
            &server_name,
            &server_name_len,
            &port_number,
            &ca_path,
            &key_path,
            &cert_path,
            &alpn_protocol,
            &client_id,
            &client_id_len,
            &keep_alive_time,
            &on_connect,
            &on_disconnect)) {
        return NULL;
    }

    struct mqtt_python_connection *connection = aws_mem_acquire(allocator, sizeof(struct mqtt_python_connection));
    if (!connection) {
        return PyErr_NoMemory();
    }
    AWS_ZERO_STRUCT(*connection);

    if (!elg_capsule || !PyCapsule_CheckExact(elg_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }
    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);

    if (on_connect && PyCallable_Check(on_connect)) {
        Py_INCREF(on_connect);
        connection->on_connect = on_connect;
    }

    if (on_disconnect && PyCallable_Check(on_disconnect)) {
        Py_INCREF(on_disconnect);
        connection->on_disconnect = on_disconnect;
    }

    struct aws_tls_ctx_options tls_ctx_opt;
    aws_tls_ctx_options_init_client_mtls(&tls_ctx_opt, cert_path, key_path);
    if (ca_path) {
        aws_tls_ctx_options_override_default_trust_store(&tls_ctx_opt, NULL, ca_path);
    }
    if (alpn_protocol) {
        aws_tls_ctx_options_set_alpn_list(&tls_ctx_opt, alpn_protocol);
    }

    AWS_ZERO_STRUCT(connection->socket_options);
    connection->socket_options.connect_timeout_ms = 3000;
    connection->socket_options.type = AWS_SOCKET_STREAM;
    connection->socket_options.domain = AWS_SOCKET_IPV4;

    struct aws_mqtt_client_connection_callbacks callbacks;
    AWS_ZERO_STRUCT(callbacks);
    callbacks.on_connection_failed = s_on_connect_failed;
    callbacks.on_connack = s_on_connect;
    callbacks.on_disconnect = s_on_disconnect;
    callbacks.user_data = connection;

    aws_mqtt_client_init(&connection->client, allocator, elg);

    struct aws_byte_cursor server_name_cur = aws_byte_cursor_from_array(server_name, server_name_len);

    connection->connection = aws_mqtt_client_connection_new(
        &connection->client, callbacks, &server_name_cur, port_number, &connection->socket_options, &tls_ctx_opt);

    if (!connection->connection) {
        return PyErr_NoMemory();
    }

    struct aws_byte_cursor client_id_cur = aws_byte_cursor_from_array(client_id, client_id_len);
    aws_mqtt_client_connection_connect(connection->connection, &client_id_cur, true, keep_alive_time);

    return PyCapsule_New(connection, s_capsule_name_mqtt_client_connection, s_mqtt_python_connection_destructor);
}

/*******************************************************************************
 * Configuration
 ******************************************************************************/

PyObject *mqtt_set_will(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule = NULL;
    const char *topic;
    Py_ssize_t topic_len;
    const char *payload;
    Py_ssize_t payload_len;
    uint8_t qos_val = AWS_MQTT_QOS_AT_MOST_ONCE;
    PyObject *retain = NULL;

    if (!PyArg_ParseTuple(
            args, "Os#s#bO", &impl_capsule, &topic, &topic_len, &payload, &payload_len, &qos_val, &retain)) {
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

    struct aws_byte_cursor topic_cursor = aws_byte_cursor_from_array(topic, topic_len);
    enum aws_mqtt_qos qos = (enum aws_mqtt_qos)qos_val;
    struct aws_byte_cursor payload_cursor = aws_byte_cursor_from_array(payload, payload_len);

    aws_mqtt_client_connection_set_will(connection->connection, &topic_cursor, qos, retain == Py_True, &payload_cursor);

    Py_RETURN_NONE;
}

PyObject *mqtt_set_login(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule = NULL;
    const char *username;
    Py_ssize_t username_len;
    const char *password;
    Py_ssize_t password_len;

    if (!PyArg_ParseTuple(
            args, "Os#z#", &impl_capsule, &username, &username_len, &password, &password_len)) {
        return NULL;
    }

    if (!impl_capsule || !PyCapsule_CheckExact(impl_capsule)) {
        PyErr_SetNone(PyExc_TypeError);
        return NULL;
    }

    struct mqtt_python_connection *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);

    struct aws_byte_cursor username_cursor = aws_byte_cursor_from_array(username, username_len);

    struct aws_byte_cursor password_cursor;
    struct aws_byte_cursor *password_cursor_ptr = NULL;
    if (password) {
        password_cursor = aws_byte_cursor_from_array(password, password_len);
        password_cursor_ptr = &password_cursor;
    }

    aws_mqtt_client_connection_set_login(connection->connection, &username_cursor, password_cursor_ptr);

    Py_RETURN_NONE;
}

/*******************************************************************************
 * Publish
 ******************************************************************************/

struct publish_complete_userdata {
    Py_buffer payload;
    PyObject *callback;
};

static void s_publish_complete(struct aws_mqtt_client_connection *connection, void *userdata) {

    struct publish_complete_userdata *metadata = userdata;
    if (metadata) {

        if (metadata->callback) {

            PyGILState_STATE state = PyGILState_Ensure();

            PyObject_CallFunction(metadata->callback, NULL);
            Py_DECREF(metadata->callback);

            PyGILState_Release(state);
        }

        PyBuffer_Release(&metadata->payload);
        aws_mem_release(aws_crt_python_get_allocator(), metadata);
    }
}

PyObject *mqtt_publish(PyObject *self, PyObject *args) {
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
            return PyErr_NoMemory();
        }

        memcpy(&metadata->payload, &payload_stack, sizeof(Py_buffer));
        metadata->callback = puback_callback;

        payload_cursor = aws_byte_cursor_from_array(metadata->payload.buf, metadata->payload.len);
    }

    struct aws_byte_cursor topic_cursor = aws_byte_cursor_from_array(topic, topic_len);
    enum aws_mqtt_qos qos = (enum aws_mqtt_qos)qos_val;

    aws_mqtt_client_connection_publish(
        connection->connection, &topic_cursor, qos, retain == Py_True, &payload_cursor, s_publish_complete, metadata);

    Py_RETURN_NONE;
}

/*******************************************************************************
 * Callback
 ******************************************************************************/

static void s_subscribe_callback(
    struct aws_mqtt_client_connection *connection,
    const struct aws_byte_cursor *topic,
    const struct aws_byte_cursor *payload,
    void *user_data) {

    (void)connection;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *callback = user_data;

    PyObject *result = PyObject_CallFunction(
        callback, "(NN)", PyString_FromAwsByteCursor(topic), PyString_FromAwsByteCursor(payload));

    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        abort();
    }
    Py_XDECREF(result);

    PyGILState_Release(state);
}

static void s_suback_callback(struct aws_mqtt_client_connection *connection, void *userdata) {
    (void)connection;
    PyObject *unsuback_callback = userdata;

    if (unsuback_callback) {

        PyGILState_STATE state = PyGILState_Ensure();

        PyObject_CallFunction(unsuback_callback, NULL);
        Py_DECREF(unsuback_callback);

        PyGILState_Release(state);
    }
}

PyObject *mqtt_subscribe(PyObject *self, PyObject *args) {
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

    struct mqtt_python_connection *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);

    if (qos_val > 3) {
        PyErr_SetNone(PyExc_ValueError);
    }

    struct aws_byte_cursor topic_filter = aws_byte_cursor_from_array(topic, topic_len);
    int result = aws_mqtt_client_connection_subscribe(
        connection->connection,
        &topic_filter,
        qos_val,
        s_subscribe_callback,
        callback,
        s_suback_callback,
        suback_callback);

    return PyBool_FromAwsResult(result);
}

/*******************************************************************************
 * Unsubscribe
 ******************************************************************************/

PyObject *mqtt_unsubscribe(PyObject *self, PyObject *args) {
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
    int result =
        aws_mqtt_client_connection_unsubscribe(connection->connection, &filter, s_suback_callback, unsuback_callback);

    return PyBool_FromAwsResult(result);
}

/*******************************************************************************
 * Disconnect
 ******************************************************************************/

PyObject *mqtt_disconnect(PyObject *self, PyObject *args) {
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

    int result = aws_mqtt_client_connection_disconnect(connection->connection);

    return PyBool_FromAwsResult(result);
}
