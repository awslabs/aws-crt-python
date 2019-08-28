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

struct mqtt_connection_binding {
    struct aws_mqtt_client_connection *native;

    PyObject *on_connect;

    /* Dependencies that must outlive this */
    PyObject *on_connection_interrupted;
    PyObject *on_connection_resumed;
    PyObject *client;
};

static void s_mqtt_python_connection_finish_destruction(struct mqtt_connection_binding *py_connection) {
    aws_mqtt_client_connection_destroy(py_connection->native);

    Py_DECREF(py_connection->on_connection_interrupted);
    Py_DECREF(py_connection->on_connection_resumed);
    Py_DECREF(py_connection->client);

    aws_mem_release(aws_py_get_allocator(), py_connection);
}

static void s_mqtt_python_connection_destructor_on_disconnect(
    struct aws_mqtt_client_connection *connection,
    void *userdata) {

    (void)connection;
    struct mqtt_connection_binding *py_connection = userdata;

    PyGILState_STATE state = PyGILState_Ensure();
    s_mqtt_python_connection_finish_destruction(py_connection);
    PyGILState_Release(state);
}

static void s_mqtt_python_connection_destructor(PyObject *connection_capsule) {

    struct mqtt_connection_binding *py_connection =
        PyCapsule_GetPointer(connection_capsule, s_capsule_name_mqtt_client_connection);
    assert(py_connection);

    if (aws_mqtt_client_connection_disconnect(
            py_connection->native, s_mqtt_python_connection_destructor_on_disconnect, py_connection)) {

        /* If this returns an error, we should immediately destroy the connection */
        s_mqtt_python_connection_finish_destruction(py_connection);
    }
}

static void s_on_connection_interrupted(struct aws_mqtt_client_connection *connection, int error_code, void *userdata) {

    (void)connection;

    struct mqtt_connection_binding *py_connection = userdata;

    if (py_connection->on_connection_interrupted == Py_None) {
        return;
    }

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(py_connection->on_connection_interrupted, "(I)", error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    PyGILState_Release(state);
}

static void s_on_connection_resumed(
    struct aws_mqtt_client_connection *connection,
    enum aws_mqtt_connect_return_code return_code,
    bool session_present,
    void *userdata) {

    (void)connection;

    struct mqtt_connection_binding *py_connection = userdata;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(
        py_connection->on_connection_resumed, "(IN)", return_code, PyBool_FromLong(session_present));
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    PyGILState_Release(state);
}

PyObject *aws_py_mqtt_client_connection_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *client_py;
    PyObject *on_connection_interrupted;
    PyObject *on_connection_resumed;
    if (!PyArg_ParseTuple(args, "OOO", &client_py, &on_connection_interrupted, &on_connection_resumed)) {
        return NULL;
    }

    struct aws_mqtt_client *client = aws_py_get_mqtt_client(client_py);
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

    py_connection->native = aws_mqtt_client_connection_new(client);
    if (!py_connection->native) {
        PyErr_SetAwsLastError();
        goto connection_new_failed;
    }

    if (aws_mqtt_client_connection_set_connection_interruption_handlers(
            py_connection->native,
            s_on_connection_interrupted,
            py_connection,
            s_on_connection_resumed,
            py_connection)) {

        PyErr_SetAwsLastError();
        goto set_interruption_failed;
    }

    PyObject *capsule =
        PyCapsule_New(py_connection, s_capsule_name_mqtt_client_connection, s_mqtt_python_connection_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    /* From hereon, nothing will fail */

    py_connection->on_connection_interrupted = on_connection_interrupted;
    Py_INCREF(py_connection->on_connection_interrupted);
    py_connection->on_connection_resumed = on_connection_resumed;
    Py_INCREF(py_connection->on_connection_resumed);
    py_connection->client = client_py;
    Py_INCREF(py_connection->client);

    return capsule;

capsule_new_failed:
set_interruption_failed:
    aws_mqtt_client_connection_destroy(py_connection->native);
connection_new_failed:
    aws_mem_release(allocator, py_connection);
    return NULL;
}

struct aws_mqtt_client_connection *aws_py_get_mqtt_client_connection(PyObject *mqtt_connection) {
    struct aws_mqtt_client_connection *native = NULL;

    PyObject *binding_capsule = PyObject_BorrowAttrString(mqtt_connection, "_binding");
    if (binding_capsule) {
        struct mqtt_connection_binding *binding =
            PyCapsule_GetPointer(binding_capsule, s_capsule_name_mqtt_client_connection);
        if (binding) {
            native = binding->native;
            assert(native);
        }
    }

    return native;
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

    (void)connection;

    struct mqtt_connection_binding *py_connection = user_data;

    if (py_connection->on_connect) {
        PyGILState_STATE state = PyGILState_Ensure();

        PyObject *callback = py_connection->on_connect;
        py_connection->on_connect = NULL;

        PyObject *result =
            PyObject_CallFunction(callback, "(IIN)", error_code, return_code, PyBool_FromLong(session_present));
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }

        Py_XDECREF(callback);

        PyGILState_Release(state);
    }
}

/* If unsuccessful, false is returned and a Python error has been set */
bool s_set_will(struct aws_mqtt_client_connection *connection, PyObject *will) {
    assert(will && (will != Py_None));

    PyObject *py_topic = PyObject_BorrowAttrString(will, "topic");
    struct aws_byte_cursor topic = aws_byte_cursor_from_pystring(py_topic);
    if (!topic.ptr) {
        PyErr_SetString(PyExc_TypeError, "Will.topic is invalid");
        return false;
    }

    PyObject *py_qos = PyObject_BorrowAttrString(will, "qos");
    if (!py_qos || !PyIntEnum_Check(py_qos)) {
        PyErr_SetString(PyExc_TypeError, "Will.qos is invalid");
        return false;
    }
    enum aws_mqtt_qos qos = (enum aws_mqtt_qos)PyIntEnum_AsLong(py_qos);

    PyObject *py_payload = PyObject_BorrowAttrString(will, "payload");
    struct aws_byte_cursor payload = aws_byte_cursor_from_pystring(py_payload);
    if (!payload.ptr) {
        PyErr_SetString(PyExc_TypeError, "Will.payload is invalid");
        return false;
    }

    PyObject *py_retain = PyObject_BorrowAttrString(will, "retain");
    if (!PyBool_Check(py_retain)) {
        PyErr_SetString(PyExc_TypeError, "Will.retain is invalid");
        return false;
    }
    bool retain = py_retain == Py_True;

    if (aws_mqtt_client_connection_set_will(connection, &topic, qos, retain, &payload)) {
        PyErr_SetAwsLastError();
        return false;
    }

    return true;
}

PyObject *aws_py_mqtt_client_connection_connect(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    const char *client_id;
    Py_ssize_t client_id_len;
    const char *server_name;
    Py_ssize_t server_name_len;
    uint16_t port_number;
    PyObject *tls_ctx_py;
    uint16_t keep_alive_time;
    uint32_t ping_timeout;
    PyObject *will;
    const char *username;
    Py_ssize_t username_len;
    const char *password;
    Py_ssize_t password_len;
    PyObject *on_connect;
    if (!PyArg_ParseTuple(
            args,
            "Os#s#HOHIOz#z#O",
            &impl_capsule,
            &client_id,
            &client_id_len,
            &server_name,
            &server_name_len,
            &port_number,
            &tls_ctx_py,
            &keep_alive_time,
            &ping_timeout,
            &will,
            &username,
            &username_len,
            &password,
            &password_len,
            &on_connect)) {
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

    struct aws_socket_options socket_options = {
        .connect_timeout_ms = 3000,
        .type = AWS_SOCKET_STREAM,
        .domain = AWS_SOCKET_IPV4,
    };

    struct aws_byte_cursor server_name_cur = aws_byte_cursor_from_array(server_name, server_name_len);

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

    struct aws_tls_ctx *tls_ctx = NULL;
    struct aws_tls_connection_options tls_options;
    AWS_ZERO_STRUCT(tls_options);

    /* From hereon, we need to clean up if errors occur */

    if (tls_ctx_py != Py_None) {
        tls_ctx = aws_py_get_tls_ctx(tls_ctx_py);
        if (!tls_ctx) {
            goto error;
        }

        aws_tls_connection_options_init_from_ctx(&tls_options, tls_ctx);
        struct aws_allocator *allocator = aws_py_get_allocator();
        struct aws_byte_cursor server_name_cur = aws_byte_cursor_from_c_str(server_name);
        if (aws_tls_connection_options_set_server_name(&tls_options, allocator, &server_name_cur)) {
            PyErr_SetAwsLastError();
            goto error;
        }
    }

    if (on_connect != Py_None) {
        Py_INCREF(on_connect);
        py_connection->on_connect = on_connect;
    }

    struct aws_byte_cursor client_id_cur = aws_byte_cursor_from_array(client_id, client_id_len);
    struct aws_mqtt_connection_options options = {.host_name = server_name_cur,
                                                  .port = port_number,
                                                  .socket_options = &socket_options,
                                                  .tls_options = tls_ctx ? &tls_options : NULL,
                                                  .client_id = client_id_cur,
                                                  .keep_alive_time_secs = keep_alive_time,
                                                  .ping_timeout_ms = ping_timeout,
                                                  .on_connection_complete = s_on_connect,
                                                  .user_data = py_connection,
                                                  .clean_session = true};
    if (aws_mqtt_client_connection_connect(py_connection->native, &options)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    Py_RETURN_NONE;

error:
    aws_tls_connection_options_clean_up(&tls_options);
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
    Py_buffer topic;
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
    assert(metadata);

    PyGILState_STATE state = PyGILState_Ensure();

    if (metadata->callback != Py_None) {
        PyObject *result = PyObject_CallFunction(metadata->callback, "(H)", packet_id);
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
    }

    Py_DECREF(metadata->callback);
    PyBuffer_Release(&metadata->topic);
    PyBuffer_Release(&metadata->payload);

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

    metadata->topic = topic_stack;
    metadata->payload = payload_stack;
    metadata->callback = puback_callback;
    Py_INCREF(metadata->callback);

    struct aws_byte_cursor topic_cursor;
    topic_cursor = aws_byte_cursor_from_array(metadata->topic.buf, metadata->topic.len);

    struct aws_byte_cursor payload_cursor;
    payload_cursor = aws_byte_cursor_from_array(metadata->payload.buf, metadata->payload.len);

    enum aws_mqtt_qos qos = (enum aws_mqtt_qos)qos_val;

    uint16_t msg_id = aws_mqtt_client_connection_publish(
        connection->native, &topic_cursor, qos, retain == Py_True, &payload_cursor, s_publish_complete, metadata);

    if (msg_id == 0) {
        PyErr_SetAwsLastError();
        goto publish_failed;
    }

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
    void *user_data) {

    (void)connection;

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *callback = user_data;

    PyObject *result = PyObject_CallFunction(
        callback,
        "(NN)",
        PyString_FromAwsByteCursor(topic),
        PyBytes_FromStringAndSize((const char *)payload->ptr, (Py_ssize_t)payload->len));

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
    PyGILState_STATE state = PyGILState_Ensure();

    const char *topic_str = (const char *)topic->ptr;
    Py_ssize_t topic_len = topic->len;
    PyObject *result = PyObject_CallFunction(callback, "(Hs#b)", packet_id, topic_str, topic_len, qos);
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

    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(callback, "(H)", packet_id);
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
 * Ping
 ******************************************************************************/

PyObject *aws_py_mqtt_client_connection_ping(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *impl_capsule;
    if (!PyArg_ParseTuple(args, "O", &impl_capsule)) {
        return NULL;
    }

    struct mqtt_connection_binding *connection =
        PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt_client_connection);
    if (!connection) {
        return NULL;
    }

    int err = aws_mqtt_client_connection_ping(connection->native);
    if (err) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

/*******************************************************************************
 * Disconnect
 ******************************************************************************/

static void s_on_disconnect(struct aws_mqtt_client_connection *connection, void *user_data) {

    (void)connection;

    PyObject *on_disconnect = user_data;

    if (on_disconnect) {
        PyGILState_STATE state = PyGILState_Ensure();

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
