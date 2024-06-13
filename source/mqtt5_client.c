/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "mqtt5_client.h"
#include "http.h"
#include "io.h"

#include <aws/http/proxy.h>
#include <aws/io/socket.h>
#include <aws/io/tls_channel_handler.h>
#include <aws/mqtt/v5/mqtt5_client.h>
#include <aws/mqtt/v5/mqtt5_types.h>

#include <stdio.h>

static const char *s_capsule_name_mqtt5_client = "aws_mqtt5_client";
static const char *s_capsule_name_ws_handshake_transform_data = "aws_ws_handshake_transform_data";

static const char *AWS_PYOBJECT_KEY_CLIENT_OPTIONS = "ClientOptions";
static const char *AWS_PYOBJECT_KEY_UNSUBSCRIBE_PACKET = "UnsubscribePacket";
static const char *AWS_PYOBJECT_KEY_DISCONNECT_PACKET = "DisconnectPacket";
static const char *AWS_PYOBJECT_KEY_PUBLISH_PACKET = "PublishPacket";
static const char *AWS_PYOBJECT_KEY_SUBSCRIBE_PACKET = "SubscribePacket";
static const char *AWS_PYOBJECT_KEY_CONNECT_PACKET = "ConnectPacket";
static const char *AWS_PYOBJECT_KEY_WILL_PACKET = "WillPacket";
static const char *AWS_PYOBJECT_KEY_SUBSCRIPTION = "Subscription";
static const char *AWS_PYOBJECT_KEY_USER_PROPERTIES = "user_properties";
static const char *AWS_PYOBJECT_KEY_REASON_CODE = "reason_code";
static const char *AWS_PYOBJECT_KEY_NAME = "name";
static const char *AWS_PYOBJECT_KEY_VALUE = "value";
static const char *AWS_PYOBJECT_KEY_SESSION_EXPIRY_INTERVAL_SEC = "session_expiry_interval_sec";
static const char *AWS_PYOBJECT_KEY_MESSAGE_EXPIRY_INTERVAL_SEC = "message_expiry_interval_sec";
static const char *AWS_PYOBJECT_KEY_REQUEST_PROBLEM_INFORMATION = "request_problem_information";
static const char *AWS_PYOBJECT_KEY_REQUEST_RESPONSE_INFORMATION = "request_response_information";
static const char *AWS_PYOBJECT_KEY_RECEIVE_MAXIMUM = "receive_maximum";
static const char *AWS_PYOBJECT_KEY_MAXIMUM_PACKET_SIZE = "maximum_packet_size";
static const char *AWS_PYOBJECT_KEY_WILL_DELAY_INTERVAL = "will_delay_interval_sec";
static const char *AWS_PYOBJECT_KEY_KEEP_ALIVE_INTERVAL_SEC = "keep_alive_interval_sec";
static const char *AWS_PYOBJECT_KEY_SUBSCRIPTIONS = "subscriptions";
static const char *AWS_PYOBJECT_KEY_SUBSCRIPTION_IDENTIFIER = "subscription_identifier";
static const char *AWS_PYOBJECT_KEY_TOPIC_ALIAS = "topic_alias";
static const char *AWS_PYOBJECT_KEY_TOPIC_FILTER = "topic_filter";
static const char *AWS_PYOBJECT_KEY_TOPIC_FILTERS = "topic_filters";
static const char *AWS_PYOBJECT_KEY_QOS = "qos";
static const char *AWS_PYOBJECT_KEY_NO_LOCAL = "no_local";
static const char *AWS_PYOBJECT_KEY_RETAIN_AS_PUBLISHED = "retain_as_published";
static const char *AWS_PYOBJECT_KEY_RETAIN_HANDLING_TYPE = "retain_handling_type";
static const char *AWS_PYOBJECT_KEY_PAYLOAD_FORMAT_INDICATOR = "payload_format_indicator";
static const char *AWS_PYOBJECT_KEY_SESSION_BEHAVIOR = "session_behavior";
static const char *AWS_PYOBJECT_KEY_EXTENDED_VALIDATION_AND_FLOW_CONTROL =
    "extended_validation_and_flow_control_options";
static const char *AWS_PYOBJECT_KEY_OFFLINE_QUEUE_BEHAVIOR = "offline_queue_behavior";
static const char *AWS_PYOBJECT_KEY_RETRY_JITTER_MODE = "retry_jitter_mode";
static const char *AWS_PYOBJECT_KEY_MIN_RECONNECT_DELAY_MS = "min_reconnect_delay_ms";
static const char *AWS_PYOBJECT_KEY_MAX_RECONNECT_DELAY_MS = "max_reconnect_delay_ms";
static const char *AWS_PYOBJECT_KEY_MIN_CONNECTED_TIME_TO_RESET_RECONNECT_DELAY_MS =
    "min_connected_time_to_reset_reconnect_delay_ms";
static const char *AWS_PYOBJECT_KEY_PING_TIMEOUT_MS = "ping_timeout_ms";
static const char *AWS_PYOBJECT_KEY_CONNACK_TIMEOUT_MS = "connack_timeout_ms";
static const char *AWS_PYOBJECT_KEY_ACK_TIMEOUT_SECONDS = "ack_timeout_seconds";

#define KEEP_ALIVE_INTERVAL_SECONDS 1200

int PyObject_GetIntEnum(PyObject *o, const char *attr_name) {

    if (!PyLong_Check(o)) {
        PyErr_Format(PyExc_TypeError, "%s is not a valid enum", attr_name);
        return -1;
    }

    return PyLong_AsLong(o);
}
struct mqtt5_client_binding {
    struct aws_mqtt5_client *native;
    PyObject *client_core;
};

/* Called on either failed client creation or by the client upon normal client termination */
static void s_mqtt5_client_on_terminate(void *user_data) {
    struct mqtt5_client_binding *client = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    if (client->client_core != NULL) {
        // Make sure to release the python client object
        Py_XDECREF(client->client_core);
    }
    aws_mem_release(aws_py_get_allocator(), client);
    PyGILState_Release(state);
}

/* Called when capsule's refcount hits 0 */
static void s_mqtt5_python_client_destructor(PyObject *client_capsule) {
    struct mqtt5_client_binding *client = PyCapsule_GetPointer(client_capsule, s_capsule_name_mqtt5_client);
    assert(client);

    if (client->native != NULL) {
        /* If client is not NULL, it can be shutdown and cleaned normally */
        aws_mqtt5_client_release(client->native);
        client->native = NULL;
    } else {
        /* A failed client that must be cleaned up directly */
        s_mqtt5_client_on_terminate(client);
    }
}

/* PyErr_Occurred() must be called to check if anything went wrong after using this function. */
void aws_init_named_aws_byte_cursor_from_PyObject(
    PyObject *o,
    const char *class_name,
    const char *attr_name,
    struct aws_byte_cursor *byte_cursor_out) {
    PyObject *attr = PyObject_GetAttrString(o, attr_name);
    if (!attr) {
        PyErr_Format(PyExc_AttributeError, "'%s.%s' attribute not found", class_name, attr_name);
        return;
    }

    if (attr == Py_None) {
        PyErr_Format(PyExc_TypeError, "'%s.%s' is set to None", class_name, attr_name);
        goto done;
    }

    *byte_cursor_out = aws_byte_cursor_from_pyunicode(attr);
    if (!byte_cursor_out->ptr) {
        PyErr_Format(PyExc_TypeError, "'%s.%s' is not a valid string", class_name, attr_name);
        goto done;
    }

/* If the attribute doesn't exist or was set to None */
done:
    Py_XDECREF(attr);
}

/* PyErr_Occurred() must be called to check if anything went wrong after using this function. */
static struct aws_mqtt5_user_property *aws_get_optional_user_properties_from_PyObject(
    PyObject *attr,
    size_t *user_property_count_out) {

    if (attr == Py_None) {
        /* This is not an error */
        return NULL;
    }

    if (!PySequence_Check(attr)) {
        PyErr_Format(PyExc_TypeError, "user_properties must be a list or tuple");
        return NULL;
    }

    Py_ssize_t user_property_count = PySequence_Size(attr);
    if (user_property_count <= 0) {
        return NULL;
    }

    /*
     * This allocated memory must be cleaned up within this function if NULL is returned or
     * outside of this function if a pointer is successfully returned
     */
    struct aws_mqtt5_user_property *user_properties_tmp =
        aws_mem_calloc(aws_py_get_allocator(), (size_t)user_property_count, sizeof(struct aws_mqtt5_user_property));

    PyObject *property_py;
    for (Py_ssize_t i = 0; i < user_property_count; ++i) {
        property_py = PySequence_GetItem(attr, i);
        aws_init_named_aws_byte_cursor_from_PyObject(
            property_py, AWS_PYOBJECT_KEY_USER_PROPERTIES, AWS_PYOBJECT_KEY_NAME, &user_properties_tmp[i].name);
        if (PyErr_Occurred()) {
            Py_XDECREF(property_py);
            goto error;
        }
        aws_init_named_aws_byte_cursor_from_PyObject(
            property_py, AWS_PYOBJECT_KEY_USER_PROPERTIES, AWS_PYOBJECT_KEY_VALUE, &user_properties_tmp[i].value);
        if (PyErr_Occurred()) {
            Py_XDECREF(property_py);
            goto error;
        }
        Py_XDECREF(property_py);
    }

    *user_property_count_out = (size_t)user_property_count;
    return user_properties_tmp;

error:
    aws_mem_release(aws_py_get_allocator(), user_properties_tmp);
    user_properties_tmp = NULL;
    return NULL;
}

static PyObject *s_aws_set_user_properties_to_PyObject(
    const struct aws_mqtt5_user_property *user_properties,
    size_t user_properties_count) {
    PyObject *user_properties_list = PyList_New(user_properties_count);
    if (!user_properties_list) {
        return NULL;
    }

    for (size_t i = 0; i < user_properties_count; ++i) {
        PyObject *tuple = Py_BuildValue(
            "(s#s#)",
            user_properties[i].name.ptr,
            user_properties[i].name.len,
            user_properties[i].value.ptr,
            user_properties[i].value.len);
        if (!tuple) {
            PyErr_Format(PyExc_TypeError, "Publish Packet User Property index %zu is not a valid string", i);
            Py_XDECREF(user_properties_list);
            return NULL;
        }
        PyList_SetItem(user_properties_list, i, tuple); /* Steals reference to tuple */
    }
    return user_properties_list;
}

/*******************************************************************************
 * Publish Handler
 ******************************************************************************/

static void s_on_publish_received(const struct aws_mqtt5_packet_publish_view *publish_packet, void *user_data) {

    if (!user_data) {
        return;
    }
    struct mqtt5_client_binding *client = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* These must be DECREF'd when function ends */
    PyObject *result = NULL;
    PyObject *subscription_identifier_list = NULL;
    PyObject *user_properties_list = NULL;

    size_t subscription_identifier_count = publish_packet->subscription_identifier_count;
    size_t user_property_count = publish_packet->user_property_count;

    /* Create list of uint32_t subscription identifier tuples */
    subscription_identifier_list = PyList_New(subscription_identifier_count);
    if (!subscription_identifier_list) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto cleanup;
    }

    for (size_t i = 0; i < subscription_identifier_count; ++i) {
        PyList_SetItem(
            subscription_identifier_list,
            i,
            PyLong_FromLongLong(publish_packet->subscription_identifiers[i])); /* Steals a reference */
    }

    user_properties_list = s_aws_set_user_properties_to_PyObject(publish_packet->user_properties, user_property_count);
    if (PyErr_Occurred()) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto cleanup;
    }

    result = PyObject_CallMethod(
        client->client_core,
        "_on_publish",
        "(y#iOs#OiOIOHs#y#Os#O)",
        /* y */ publish_packet->payload.ptr,
        /* # */ publish_packet->payload.len,
        /* i */ (int)publish_packet->qos,
        /* O */ publish_packet->retain ? Py_True : Py_False,
        /* s */ publish_packet->topic.ptr,
        /* # */ publish_packet->topic.len,
        /* O */ publish_packet->payload_format ? Py_True : Py_False,
        /* i */ (int)(publish_packet->payload_format ? *publish_packet->payload_format : 0),
        /* O */ publish_packet->message_expiry_interval_seconds ? Py_True : Py_False,
        /* I */
        (unsigned int)(publish_packet->message_expiry_interval_seconds
                           ? *publish_packet->message_expiry_interval_seconds
                           : 0),
        /* O */ publish_packet->topic_alias ? Py_True : Py_False,
        /* H */ (unsigned short)(publish_packet->topic_alias ? *publish_packet->topic_alias : 0),
        /* s */ publish_packet->response_topic ? publish_packet->response_topic->ptr : NULL,
        /* # */ publish_packet->response_topic ? publish_packet->response_topic->len : 0,
        /* y */ publish_packet->correlation_data ? publish_packet->correlation_data->ptr : NULL,
        /* # */ publish_packet->correlation_data ? publish_packet->correlation_data->len : 0,
        /* O */ subscription_identifier_count > 0 ? subscription_identifier_list : Py_None,
        /* s */ publish_packet->content_type ? publish_packet->content_type->ptr : NULL,
        /* # */ publish_packet->content_type ? publish_packet->content_type->len : 0,
        /* O */ user_property_count > 0 ? user_properties_list : Py_None);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

cleanup:
    Py_XDECREF(result);
    Py_XDECREF(subscription_identifier_list);
    Py_XDECREF(user_properties_list);
    PyGILState_Release(state);
}

/*******************************************************************************
 * Lifecycle Event Handler
 ******************************************************************************/

static void s_lifecycle_event_stopped(struct mqtt5_client_binding *client) {
    if (!client || !client->client_core) {
        return;
    }

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(client->client_core, "_on_lifecycle_stopped", NULL);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_XDECREF(result);

    PyGILState_Release(state);
}

static void s_lifecycle_event_attempting_connect(struct mqtt5_client_binding *client) {
    if (!client) {
        return;
    }

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(client->client_core, "_on_lifecycle_attempting_connect", NULL);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_XDECREF(result);

    PyGILState_Release(state);
}

static void s_lifecycle_event_connection_success(
    struct mqtt5_client_binding *client,
    const struct aws_mqtt5_packet_connack_view *connack,
    const struct aws_mqtt5_negotiated_settings *settings) {
    if (!client) {
        return;
    }

    /* These must be DECREF'd when function ends */
    PyObject *user_properties_list = NULL;
    PyObject *result = NULL;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    size_t user_property_count = connack->user_property_count;

    user_properties_list = s_aws_set_user_properties_to_PyObject(connack->user_properties, user_property_count);
    if (PyErr_Occurred()) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto cleanup;
    }

    result = PyObject_CallMethod(
        client->client_core,
        "_on_lifecycle_connection_success",
        "(OiOIOHOiOOOIs#OIs#OOOOOOOOHs#s#iIHIHHHOOOOOs#)",
        /* connack packet  */
        /* O */ connack->session_present ? Py_True : Py_False,
        /* i */ (int)connack->reason_code,
        /* O */ connack->session_expiry_interval ? Py_True : Py_False,
        /* I */ (unsigned int)(connack->session_expiry_interval ? *connack->session_expiry_interval : 0),
        /* O */ connack->receive_maximum ? Py_True : Py_False,
        /* H */ (unsigned short)(connack->receive_maximum ? *connack->receive_maximum : 0),
        /* O */ connack->maximum_qos ? Py_True : Py_False,
        /* i */ (int)(connack->maximum_qos ? *connack->maximum_qos : 0),
        /* O */ connack->retain_available ? Py_True : Py_False,
        /* O */ (connack->retain_available && *connack->retain_available) ? Py_True : Py_False,
        /* O */ connack->maximum_packet_size ? Py_True : Py_False,
        /* I */ (unsigned int)(connack->maximum_packet_size ? *connack->maximum_packet_size : 0),
        /* s */ connack->assigned_client_identifier ? connack->assigned_client_identifier->ptr : NULL,
        /* # */ connack->assigned_client_identifier ? connack->assigned_client_identifier->len : 0,
        /* O */ connack->topic_alias_maximum ? Py_True : Py_False,
        /* I */ (unsigned int)(connack->topic_alias_maximum ? *connack->topic_alias_maximum : 0),
        /* s */ connack->reason_string ? connack->reason_string->ptr : NULL,
        /* # */ connack->reason_string ? connack->reason_string->len : 0,
        /* O */ user_property_count > 0 ? user_properties_list : Py_None,
        /* O */ connack->wildcard_subscriptions_available ? Py_True : Py_False,
        /* O */
        (connack->wildcard_subscriptions_available && *connack->wildcard_subscriptions_available) ? Py_True : Py_False,
        /* O */ connack->subscription_identifiers_available ? Py_True : Py_False,
        /* O */
        (connack->subscription_identifiers_available && *connack->subscription_identifiers_available) ? Py_True
                                                                                                      : Py_False,
        /* O */ connack->shared_subscriptions_available ? Py_True : Py_False,
        /* O */
        (connack->shared_subscriptions_available && *connack->shared_subscriptions_available) ? Py_True : Py_False,
        /* O */ connack->server_keep_alive ? Py_True : Py_False,
        /* H */ (unsigned short)(connack->server_keep_alive ? *connack->server_keep_alive : 0),
        /* s */ connack->response_information ? connack->response_information->ptr : NULL,
        /* # */ connack->response_information ? connack->response_information->len : 0,
        /* s */ connack->server_reference ? connack->server_reference->ptr : NULL,
        /* # */ connack->server_reference ? connack->server_reference->len : 0,
        /* negotiated settings */
        /* i */ (int)settings->maximum_qos,
        /* I */ (unsigned int)settings->session_expiry_interval,
        /* H */ (unsigned short)settings->receive_maximum_from_server,
        /* I */ (unsigned int)settings->maximum_packet_size_to_server,
        /* H */ (unsigned short)settings->topic_alias_maximum_to_server,
        /* H */ (unsigned short)settings->topic_alias_maximum_to_client,
        /* H */ (unsigned short)settings->server_keep_alive,
        /* O */ settings->retain_available ? Py_True : Py_False,
        /* O */ settings->wildcard_subscriptions_available ? Py_True : Py_False,
        /* O */ settings->subscription_identifiers_available ? Py_True : Py_False,
        /* O */ settings->shared_subscriptions_available ? Py_True : Py_False,
        /* O */ settings->rejoined_session ? Py_True : Py_False,
        /* s */ settings->client_id_storage.len > 0 ? settings->client_id_storage.buffer : NULL,
        /* # */ settings->client_id_storage.len);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
cleanup:
    Py_XDECREF(result);
    Py_XDECREF(user_properties_list);

    PyGILState_Release(state);
}

static void s_lifecycle_event_connection_failure(
    struct mqtt5_client_binding *client,
    const struct aws_mqtt5_packet_connack_view *connack,
    int error_code) {
    if (!client) {
        return;
    }

    /* These must be DECREF'd when function ends */
    PyObject *user_properties_list = NULL;
    PyObject *result = NULL;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    size_t user_property_count = 0;

    if (connack) {
        user_property_count = connack->user_property_count;

        user_properties_list = s_aws_set_user_properties_to_PyObject(connack->user_properties, user_property_count);
        if (PyErr_Occurred()) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            goto cleanup;
        }
    }

    result = PyObject_CallMethod(
        client->client_core,
        "_on_lifecycle_connection_failure",
        "(iOOiOIOHOiOOOIs#s#OOOOOOOOHs#s#)",
        /* i */ (int)error_code,
        /* O */ connack ? Py_True : Py_False,
        /* O */ (connack && connack->session_present) ? Py_True : Py_False,
        /* i */ (int)(connack ? connack->reason_code : 0),
        /* O */ (connack && connack->session_expiry_interval) ? Py_True : Py_False,
        /* I */ (unsigned int)((connack && connack->session_expiry_interval) ? *connack->session_expiry_interval : 0),
        /* O */ (connack && connack->receive_maximum) ? Py_True : Py_False,
        /* H */ (unsigned short)((connack && connack->receive_maximum) ? *connack->receive_maximum : 0),
        /* O */ (connack && connack->maximum_qos) ? Py_True : Py_False,
        /* i */ (int)((connack && connack->maximum_qos) ? *connack->maximum_qos : 0),
        /* O */ (connack && connack->retain_available) ? Py_True : Py_False,
        /* O */ (connack && connack->retain_available && *connack->retain_available) ? Py_True : Py_False,
        /* O */ (connack && connack->maximum_packet_size) ? Py_True : Py_False,
        /* I */ (unsigned int)(connack && connack->maximum_packet_size) ? *connack->maximum_packet_size : 0,
        /* s */ (connack && connack->assigned_client_identifier) ? connack->assigned_client_identifier->ptr : NULL,
        /* # */ (connack && connack->assigned_client_identifier) ? connack->assigned_client_identifier->len : 0,
        /* s */ (connack && connack->reason_string) ? connack->reason_string->ptr : NULL,
        /* # */ (connack && connack->reason_string) ? connack->reason_string->len : 0,
        /* O */ user_property_count > 0 ? user_properties_list : Py_None,
        /* O */ (connack && connack->wildcard_subscriptions_available) ? Py_True : Py_False,
        /* O */
        (connack && connack->wildcard_subscriptions_available && *connack->wildcard_subscriptions_available) ? Py_True
                                                                                                             : Py_False,
        /* O */ (connack && connack->subscription_identifiers_available) ? Py_True : Py_False,
        /* O */
        (connack && connack->subscription_identifiers_available && *connack->subscription_identifiers_available)
            ? Py_True
            : Py_False,
        /* O */ (connack && connack->shared_subscriptions_available) ? Py_True : Py_False,
        /* O */
        (connack && connack->shared_subscriptions_available && *connack->shared_subscriptions_available) ? Py_True
                                                                                                         : Py_False,
        /* O */ (connack && connack->server_keep_alive) ? Py_True : Py_False,
        /* H */ (unsigned short)(connack && connack->server_keep_alive) ? *connack->server_keep_alive : 0,
        /* s */ (connack && connack->response_information) ? connack->response_information->ptr : NULL,
        /* # */ (connack && connack->response_information) ? connack->response_information->len : 0,
        /* s */ (connack && connack->server_reference) ? connack->server_reference->ptr : NULL,
        /* # */ (connack && connack->server_reference) ? connack->server_reference->len : 0);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
cleanup:
    Py_XDECREF(result);
    Py_XDECREF(user_properties_list);

    PyGILState_Release(state);
}

static void s_lifecycle_event_disconnection(
    struct mqtt5_client_binding *client,
    const struct aws_mqtt5_packet_disconnect_view *disconnect,
    int error_code) {
    if (!client) {
        return;
    }
    /* These must be DECREF'd when function ends */
    PyObject *user_properties_list = NULL;
    PyObject *result = NULL;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    size_t user_property_count = 0;

    if (disconnect) {
        user_property_count = disconnect->user_property_count;

        user_properties_list = s_aws_set_user_properties_to_PyObject(disconnect->user_properties, user_property_count);
        if (PyErr_Occurred()) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            goto cleanup;
        }
    }

    result = PyObject_CallMethod(
        client->client_core,
        "_on_lifecycle_disconnection",
        "(iOiOIs#Os#)",
        /* i */ (int)error_code,
        /* O */ disconnect ? Py_True : Py_False,
        /* i */ (int)(disconnect ? disconnect->reason_code : 0),
        /* O */ (disconnect && disconnect->session_expiry_interval_seconds) ? Py_True : Py_False,
        /* I */
        (unsigned int)((disconnect && disconnect->session_expiry_interval_seconds)
                           ? *disconnect->session_expiry_interval_seconds
                           : 0),
        /* s */ (disconnect && disconnect->reason_string) ? disconnect->reason_string->ptr : NULL,
        /* # */ (disconnect && disconnect->reason_string) ? disconnect->reason_string->len : 0,
        /* O */ user_property_count > 0 ? user_properties_list : Py_None,
        /* s */ (disconnect && disconnect->server_reference) ? disconnect->server_reference->ptr : NULL,
        /* # */ (disconnect && disconnect->server_reference) ? disconnect->server_reference->len : 0);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
cleanup:
    Py_XDECREF(result);
    Py_XDECREF(user_properties_list);

    PyGILState_Release(state);
}

static void s_lifecycle_event_callback(const struct aws_mqtt5_client_lifecycle_event *event) {
    switch (event->event_type) {
        case AWS_MQTT5_CLET_STOPPED:
            s_lifecycle_event_stopped(event->user_data);
            break;

        case AWS_MQTT5_CLET_ATTEMPTING_CONNECT:
            s_lifecycle_event_attempting_connect(event->user_data);
            break;

        case AWS_MQTT5_CLET_CONNECTION_SUCCESS:
            s_lifecycle_event_connection_success(event->user_data, event->connack_data, event->settings);
            break;

        case AWS_MQTT5_CLET_CONNECTION_FAILURE:
            s_lifecycle_event_connection_failure(event->user_data, event->connack_data, event->error_code);
            break;

        case AWS_MQTT5_CLET_DISCONNECTION:
            s_lifecycle_event_disconnection(event->user_data, event->disconnect_data, event->error_code);
            break;

        default:
            break;
    }
}

/*******************************************************************************
 * Websocket
 ******************************************************************************/

/* persistent storage for the data needed to transform the websocket handshake*/
struct ws_handshake_transform_data {
    /* Strong reference to Python Client so it can't go out of scope during transform */
    PyObject *client_core;

    struct aws_http_message *request;
    aws_mqtt5_transform_websocket_handshake_complete_fn *complete_fn;
    void *complete_ctx;

    /* Python bindings we created to wrap the native request */
    /* Necessary? */
    PyObject *request_binding_py;
    PyObject *headers_binding_py;
};

void s_mqtt5_ws_handshake_transform_data_destructor(PyObject *capsule) {
    struct ws_handshake_transform_data *ws_data =
        PyCapsule_GetPointer(capsule, s_capsule_name_ws_handshake_transform_data);

    /* Note that binding may be only partially constructed, if error occurred during setup */
    Py_XDECREF(ws_data->client_core);
    Py_XDECREF(ws_data->request_binding_py);
    Py_XDECREF(ws_data->headers_binding_py);

    aws_mem_release(aws_py_get_allocator(), ws_data);
}

/* Invoke user's websocket handshake transform function */
static void s_ws_handshake_transform(
    struct aws_http_message *request,
    void *user_data,
    aws_mqtt5_transform_websocket_handshake_complete_fn *complete_fn,
    void *complete_ctx) {

    // struct mqtt_connection_binding *connection_binding = user_data;
    struct mqtt5_client_binding *client = user_data;

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

    ws_transform_data = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct ws_handshake_transform_data));

    ws_transform_capsule = PyCapsule_New(
        ws_transform_data, s_capsule_name_ws_handshake_transform_data, s_mqtt5_ws_handshake_transform_data_destructor);
    if (!ws_transform_capsule) {
        aws_py_raise_error();
        goto done;
    }

    /* From hereon, capsule destructor will clean up anything stored within it */

    ws_transform_data->request = request;
    ws_transform_data->complete_fn = complete_fn;
    ws_transform_data->complete_ctx = complete_ctx;

    ws_transform_data->client_core = client->client_core;
    Py_INCREF(ws_transform_data->client_core);

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
        client->client_core,
        "_ws_handshake_transform",
        "(OOO)",
        /* O */ ws_transform_data->request_binding_py,
        /* O */ ws_transform_data->headers_binding_py,
        /* O */ ws_transform_capsule);

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
PyObject *aws_py_mqtt5_ws_handshake_transform_complete(PyObject *self, PyObject *args) {
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

static bool s_py_topic_aliasing_options_init(
    struct aws_mqtt5_client_topic_alias_options *topic_aliasing_options,
    PyObject *py_topic_aliasing_options) {
    AWS_ZERO_STRUCT(*topic_aliasing_options);

    bool success = false;
    PyObject *py_outbound_behavior = PyObject_GetAttrString(py_topic_aliasing_options, "outbound_behavior");
    PyObject *py_outbound_cache_max_size = PyObject_GetAttrString(py_topic_aliasing_options, "outbound_cache_max_size");
    PyObject *py_inbound_behavior = PyObject_GetAttrString(py_topic_aliasing_options, "inbound_behavior");
    PyObject *py_inbound_cache_max_size = PyObject_GetAttrString(py_topic_aliasing_options, "inbound_cache_max_size");

    if (py_outbound_behavior != NULL && !PyObject_GetAsOptionalIntEnum(
                                            py_outbound_behavior,
                                            "TopicAliasingOptions",
                                            "outbound_behavior",
                                            (int *)&topic_aliasing_options->outbound_topic_alias_behavior)) {
        if (PyErr_Occurred()) {
            goto done;
        }
    }

    if (py_outbound_cache_max_size != NULL && !PyObject_GetAsOptionalUint16(
                                                  py_outbound_cache_max_size,
                                                  "TopicAliasingOptions",
                                                  "outbound_cache_max_size",
                                                  &topic_aliasing_options->outbound_alias_cache_max_size)) {
        if (PyErr_Occurred()) {
            goto done;
        }
    }

    if (py_inbound_behavior != NULL && !PyObject_GetAsOptionalIntEnum(
                                           py_inbound_behavior,
                                           "TopicAliasingOptions",
                                           "inbound_behavior",
                                           (int *)&topic_aliasing_options->inbound_topic_alias_behavior)) {
        if (PyErr_Occurred()) {
            goto done;
        }
    }

    if (py_inbound_cache_max_size != NULL && !PyObject_GetAsOptionalUint16(
                                                 py_inbound_cache_max_size,
                                                 "TopicAliasingOptions",
                                                 "inbound_cache_max_size",
                                                 &topic_aliasing_options->inbound_alias_cache_size)) {
        if (PyErr_Occurred()) {
            goto done;
        }
    }

    success = true;

done:

    Py_XDECREF(py_outbound_behavior);
    Py_XDECREF(py_outbound_cache_max_size);
    Py_XDECREF(py_inbound_behavior);
    Py_XDECREF(py_inbound_cache_max_size);

    return success;
}

/*******************************************************************************
 * Client Init
 ******************************************************************************/

PyObject *aws_py_mqtt5_client_new(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *self_py;

    struct aws_byte_cursor host_name;
    PyObject *bootstrap_py;
    PyObject *socket_options_py;
    PyObject *tls_ctx_py;
    PyObject *proxy_options_py;
    uint32_t port;

    /* Connect Options */
    struct aws_byte_cursor client_id;          /* optional */
    PyObject *keep_alive_interval_sec_py;      /* optional uint16_t */
    struct aws_byte_cursor username;           /* optional */
    struct aws_byte_cursor password;           /* optional */
    PyObject *session_expiry_interval_sec_py;  /* optional uint32_t */
    PyObject *request_response_information_py; /* optional bool */
    PyObject *request_problem_information_py;  /* optional bool */
    PyObject *receive_maximum_py;              /* optional uint16_t */
    PyObject *maximum_packet_size_py;          /* optional uint32_t */
    PyObject *will_delay_interval_sec_py;      /* optional uint32_t */
    PyObject *user_properties_py;              /* optional */

    /* Will */
    PyObject *is_will_none_py; /* optional PublishPacket */
    PyObject *will_qos_val_py;
    Py_buffer will_payload_stack; /* Py_buffers must be released after successful PyArg_ParseTuple() calls */
    PyObject *will_retain_py;
    struct aws_byte_cursor will_topic;
    PyObject *will_payload_format_py;                  /* optional enum */
    PyObject *will_message_expiry_interval_seconds_py; /* optional uint32_t */
    PyObject *will_topic_alias_py;                     /* optional uint16_t */
    struct aws_byte_cursor will_response_topic;        /* optional */
    Py_buffer will_correlation_data_stack;             /* optional */
    struct aws_byte_cursor will_content_type;          /* optional */
    PyObject *will_user_properties_py;                 /* optional */

    PyObject *session_behavior_py;                               /* optional enum */
    PyObject *extended_validation_and_flow_control_options_py;   /* optional enum */
    PyObject *offline_queue_behavior_py;                         /* optional enum */
    PyObject *retry_jitter_mode_py;                              /* optional enum */
    PyObject *min_reconnect_delay_ms_py;                         /* optional uint64_t */
    PyObject *max_reconnect_delay_ms_py;                         /* optional uint64_t */
    PyObject *min_connected_time_to_reset_reconnect_delay_ms_py; /* optional uint64_t */
    PyObject *ping_timeout_ms_py;                                /* optional uint32_t */
    PyObject *connack_timeout_ms_py;                             /* optional uint32_t */
    PyObject *ack_timeout_seconds_py;                            /* optional uint32_t */
    PyObject *topic_aliasing_options_py;                         /* optional TopicAliasingOptions */
    /* Callbacks */
    PyObject *is_websocket_none_py;
    PyObject *client_core_py;

    if (!PyArg_ParseTuple(
            args,
            "Os#IOOOOz#Oz#z#OOOOOOOOOz*Oz#OOOz#z*z#OOOOOOOOOOOOOO",
            /* O */ &self_py,
            /* s */ &host_name.ptr,
            /* # */ &host_name.len,
            /* I */ &port,
            /* O */ &bootstrap_py,
            /* O */ &socket_options_py,
            /* O */ &tls_ctx_py,
            /* O */ &proxy_options_py,

            /* Connect Options */
            /* z */ &client_id.ptr,
            /* # */ &client_id.len,
            /* O */ &keep_alive_interval_sec_py,
            /* z */ &username.ptr,
            /* # */ &username.len,
            /* z */ &password.ptr,
            /* # */ &password.len,
            /* O */ &session_expiry_interval_sec_py,
            /* O */ &request_response_information_py,
            /* O */ &request_problem_information_py,
            /* O */ &receive_maximum_py,
            /* O */ &maximum_packet_size_py,
            /* O */ &will_delay_interval_sec_py,
            /* O */ &user_properties_py,

            /* O */ &is_will_none_py,
            /* O */ &will_qos_val_py,
            /* z* */ &will_payload_stack,
            /* O */ &will_retain_py,
            /* z */ &will_topic.ptr,
            /* # */ &will_topic.len,
            /* O */ &will_payload_format_py,
            /* O */ &will_message_expiry_interval_seconds_py,
            /* O */ &will_topic_alias_py,
            /* z */ &will_response_topic.ptr,
            /* # */ &will_response_topic.len,
            /* z* */ &will_correlation_data_stack,
            /* z */ &will_content_type.ptr,
            /* # */ &will_content_type.len,
            /* O */ &will_user_properties_py,

            /* O */ &session_behavior_py,
            /* O */ &extended_validation_and_flow_control_options_py,
            /* O */ &offline_queue_behavior_py,
            /* O */ &retry_jitter_mode_py,
            /* O */ &min_reconnect_delay_ms_py,
            /* O */ &max_reconnect_delay_ms_py,
            /* O */ &min_connected_time_to_reset_reconnect_delay_ms_py,
            /* O */ &ping_timeout_ms_py,
            /* O */ &connack_timeout_ms_py,
            /* O */ &ack_timeout_seconds_py,
            /* O */ &topic_aliasing_options_py,

            /* O */ &is_websocket_none_py,
            /* O */ &client_core_py)) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct mqtt5_client_binding *client = aws_mem_calloc(allocator, 1, sizeof(struct mqtt5_client_binding));
    // Python object that wraps a c struct and a function to call when its reference goes to zero
    PyObject *capsule = PyCapsule_New(client, s_capsule_name_mqtt5_client, s_mqtt5_python_client_destructor);
    if (!capsule) {
        aws_mem_release(allocator, client);
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */
    struct aws_tls_connection_options tls_options;
    AWS_ZERO_STRUCT(tls_options);
    struct aws_mqtt5_user_property *user_properties_tmp = NULL;
    struct aws_mqtt5_user_property *will_user_properties_tmp = NULL;

    struct aws_mqtt5_client_options client_options;
    AWS_ZERO_STRUCT(client_options);

    struct aws_mqtt5_packet_connect_view connect_options;
    AWS_ZERO_STRUCT(connect_options);

    struct aws_mqtt5_packet_publish_view will_options;
    AWS_ZERO_STRUCT(will_options);

    struct aws_http_proxy_options proxy_options;
    struct aws_mqtt5_client_topic_alias_options topic_aliasing_options;

    struct aws_tls_ctx *tls_ctx = NULL;

    client_options.connect_options = &connect_options;

    client_options.host_name = host_name;

    /* port should default similar to existing ones based on protocol unless overridden by user */
    client_options.port = port;

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        goto done;
    }
    client_options.bootstrap = bootstrap;

    struct aws_socket_options socket_options;
    if (!aws_py_socket_options_init(&socket_options, socket_options_py)) {
        goto done;
    }
    client_options.socket_options = &socket_options;

    if (proxy_options_py != Py_None) {
        if (!aws_py_http_proxy_options_init(&proxy_options, proxy_options_py)) {
            goto done;
        }
        client_options.http_proxy_options = &proxy_options;
    }

    if (tls_ctx_py != Py_None) {
        tls_ctx = aws_py_get_tls_ctx(tls_ctx_py);
        if (!tls_ctx) {
            goto done;
        }

        aws_tls_connection_options_init_from_ctx(&tls_options, tls_ctx);
        client_options.tls_options = &tls_options;
    }

    int session_behavior_tmp = 0;
    if (PyObject_GetAsOptionalIntEnum(
            session_behavior_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_SESSION_BEHAVIOR,
            &session_behavior_tmp)) {
        client_options.session_behavior = (enum aws_mqtt5_client_session_behavior_type)session_behavior_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    int extended_validation_and_flow_control_options_tmp = 0;
    if (PyObject_GetAsOptionalIntEnum(
            extended_validation_and_flow_control_options_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_EXTENDED_VALIDATION_AND_FLOW_CONTROL,
            &extended_validation_and_flow_control_options_tmp)) {
        client_options.extended_validation_and_flow_control_options =
            (enum aws_mqtt5_extended_validation_and_flow_control_options)
                extended_validation_and_flow_control_options_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    int offline_queue_behavior_tmp = 0;
    if (PyObject_GetAsOptionalIntEnum(
            offline_queue_behavior_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_OFFLINE_QUEUE_BEHAVIOR,
            &offline_queue_behavior_tmp)) {
        client_options.offline_queue_behavior =
            (enum aws_mqtt5_client_operation_queue_behavior_type)offline_queue_behavior_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    int retry_jitter_mode_tmp = 0;
    if (PyObject_GetAsOptionalIntEnum(
            retry_jitter_mode_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_RETRY_JITTER_MODE,
            &retry_jitter_mode_tmp)) {
        client_options.retry_jitter_mode = (enum aws_exponential_backoff_jitter_mode)retry_jitter_mode_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint64_t min_reconnect_delay_ms_tmp = 0;
    if (PyObject_GetAsOptionalUint64(
            min_reconnect_delay_ms_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_MIN_RECONNECT_DELAY_MS,
            &min_reconnect_delay_ms_tmp)) {
        client_options.min_reconnect_delay_ms = min_reconnect_delay_ms_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint64_t max_reconnect_delay_ms_tmp = 0;
    if (PyObject_GetAsOptionalUint64(
            max_reconnect_delay_ms_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_MAX_RECONNECT_DELAY_MS,
            &max_reconnect_delay_ms_tmp)) {
        client_options.max_reconnect_delay_ms = max_reconnect_delay_ms_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint64_t min_connected_time_to_reset_reconnect_delay_ms_tmp = 0;
    if (PyObject_GetAsOptionalUint64(
            min_connected_time_to_reset_reconnect_delay_ms_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_MIN_CONNECTED_TIME_TO_RESET_RECONNECT_DELAY_MS,
            &min_connected_time_to_reset_reconnect_delay_ms_tmp)) {
        client_options.min_reconnect_delay_ms = min_connected_time_to_reset_reconnect_delay_ms_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint32_t ping_timeout_ms_tmp = 0;
    if (PyObject_GetAsOptionalUint32(
            ping_timeout_ms_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_PING_TIMEOUT_MS,
            &ping_timeout_ms_tmp)) {
        client_options.ping_timeout_ms = ping_timeout_ms_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint32_t connack_timeout_ms_tmp = 0;
    if (PyObject_GetAsOptionalUint32(
            connack_timeout_ms_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_CONNACK_TIMEOUT_MS,
            &connack_timeout_ms_tmp)) {
        client_options.connack_timeout_ms = connack_timeout_ms_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint32_t ack_timeout_seconds_tmp = 0;
    if (PyObject_GetAsOptionalUint32(
            ack_timeout_seconds_py,
            AWS_PYOBJECT_KEY_CLIENT_OPTIONS,
            AWS_PYOBJECT_KEY_ACK_TIMEOUT_SECONDS,
            &ack_timeout_seconds_tmp)) {
        client_options.ack_timeout_seconds = ack_timeout_seconds_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    if (topic_aliasing_options_py != Py_None) {
        if (!s_py_topic_aliasing_options_init(&topic_aliasing_options, topic_aliasing_options_py)) {
            goto done;
        }
        client_options.topic_aliasing_options = &topic_aliasing_options;
    }

    /* CONNECT OPTIONS */

    connect_options.client_id = client_id;

    /* defaults to KEEP_ALIVE_INTERVAL_SECONDS unless specified by user */
    uint16_t keep_alive_interval_sec_tmp = 0;
    uint16_t *keep_alive_interval_sec_ptr = PyObject_GetAsOptionalUint16(
        keep_alive_interval_sec_py,
        AWS_PYOBJECT_KEY_CONNECT_PACKET,
        AWS_PYOBJECT_KEY_KEEP_ALIVE_INTERVAL_SEC,
        &keep_alive_interval_sec_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }
    if (keep_alive_interval_sec_ptr) {
        connect_options.keep_alive_interval_seconds = keep_alive_interval_sec_tmp;
    } else {
        connect_options.keep_alive_interval_seconds = KEEP_ALIVE_INTERVAL_SECONDS;
    }

    if (username.ptr != NULL) {
        connect_options.username = &username;
    }

    if (password.ptr != NULL) {
        connect_options.password = &password;
    }

    uint32_t session_expiry_interval_sec_tmp = 0;
    connect_options.session_expiry_interval_seconds = PyObject_GetAsOptionalUint32(
        session_expiry_interval_sec_py,
        AWS_PYOBJECT_KEY_CONNECT_PACKET,
        AWS_PYOBJECT_KEY_SESSION_EXPIRY_INTERVAL_SEC,
        &session_expiry_interval_sec_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    bool request_response_information_py_tmp = false;
    uint8_t request_response_information_py_tmp_int = 0;
    if (PyObject_GetAsOptionalBool(
            request_response_information_py,
            AWS_PYOBJECT_KEY_CONNECT_PACKET,
            AWS_PYOBJECT_KEY_REQUEST_RESPONSE_INFORMATION,
            &request_response_information_py_tmp) != NULL) {
        request_response_information_py_tmp_int = request_response_information_py_tmp;
        connect_options.request_response_information = &request_response_information_py_tmp_int;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    bool request_problem_information_tmp = false;
    uint8_t request_problem_information_tmp_int = 0;
    if (PyObject_GetAsOptionalBool(
            request_problem_information_py,
            AWS_PYOBJECT_KEY_CONNECT_PACKET,
            AWS_PYOBJECT_KEY_REQUEST_PROBLEM_INFORMATION,
            &request_problem_information_tmp) != NULL) {
        request_problem_information_tmp_int = request_problem_information_tmp;
        connect_options.request_problem_information = &request_problem_information_tmp_int;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint16_t receive_maximum_tmp = 0;
    connect_options.receive_maximum = PyObject_GetAsOptionalUint16(
        receive_maximum_py, AWS_PYOBJECT_KEY_CONNECT_PACKET, AWS_PYOBJECT_KEY_RECEIVE_MAXIMUM, &receive_maximum_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    uint32_t maximum_packet_size_tmp = 0;
    connect_options.maximum_packet_size_bytes = PyObject_GetAsOptionalUint32(
        maximum_packet_size_py,
        AWS_PYOBJECT_KEY_CONNECT_PACKET,
        AWS_PYOBJECT_KEY_MAXIMUM_PACKET_SIZE,
        &maximum_packet_size_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    uint32_t will_delay_interval_sec_tmp = 0;
    connect_options.will_delay_interval_seconds = PyObject_GetAsOptionalUint32(
        will_delay_interval_sec_py,
        AWS_PYOBJECT_KEY_CONNECT_PACKET,
        AWS_PYOBJECT_KEY_WILL_DELAY_INTERVAL,
        &will_delay_interval_sec_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    user_properties_tmp =
        aws_get_optional_user_properties_from_PyObject(user_properties_py, &connect_options.user_property_count);
    if (PyErr_Occurred()) {
        goto done;
    }
    connect_options.user_properties = user_properties_tmp;

    /* WILL */

    struct aws_mqtt5_packet_publish_view will;
    AWS_ZERO_STRUCT(will);

    int will_payload_format_tmp = 0;
    enum aws_mqtt5_payload_format_indicator will_payload_format_enum_tmp = 0;
    uint32_t will_message_expiry_interval_seconds_tmp = 0;
    struct aws_byte_cursor will_correlation_data_tmp;
    if (!PyObject_IsTrue(is_will_none_py)) {
        will.qos = PyObject_GetIntEnum(will_qos_val_py, AWS_PYOBJECT_KEY_QOS);
        if (PyErr_Occurred()) {
            goto done;
        }
        will.payload = aws_byte_cursor_from_array(will_payload_stack.buf, will_payload_stack.len);
        will.retain = PyObject_IsTrue(will_retain_py);
        will.topic = will_topic;
        if (PyObject_GetAsOptionalIntEnum(
                will_payload_format_py,
                AWS_PYOBJECT_KEY_WILL_PACKET,
                AWS_PYOBJECT_KEY_PAYLOAD_FORMAT_INDICATOR,
                &will_payload_format_tmp)) {
            will_payload_format_enum_tmp = (enum aws_mqtt5_payload_format_indicator)will_payload_format_tmp;
            will.payload_format = &will_payload_format_enum_tmp;
        }
        if (PyErr_Occurred()) {
            goto done;
        }

        will.message_expiry_interval_seconds = PyObject_GetAsOptionalUint32(
            will_message_expiry_interval_seconds_py,
            AWS_PYOBJECT_KEY_WILL_PACKET,
            AWS_PYOBJECT_KEY_MESSAGE_EXPIRY_INTERVAL_SEC,
            &will_message_expiry_interval_seconds_tmp);
        if (PyErr_Occurred()) {
            goto done;
        }

        if (will_response_topic.ptr) {
            will.response_topic = &will_response_topic;
        }

        if (will_correlation_data_stack.buf) {
            will_correlation_data_tmp =
                aws_byte_cursor_from_array(will_correlation_data_stack.buf, will_correlation_data_stack.len);
            will.correlation_data = &will_correlation_data_tmp;
        }

        if (will_content_type.ptr) {
            will.content_type = &will_content_type;
        }

        will_user_properties_tmp =
            aws_get_optional_user_properties_from_PyObject(will_user_properties_py, &will.user_property_count);
        if (PyErr_Occurred()) {
            goto done;
        }
        will.user_properties = will_user_properties_tmp;

        connect_options.will = &will;
    }

    /* CALLBACKS */

    Py_INCREF(client_core_py);
    client->client_core = client_core_py;

    /* websocket */
    if (!PyObject_IsTrue(is_websocket_none_py)) {
        client_options.websocket_handshake_transform = s_ws_handshake_transform;
        client_options.websocket_handshake_transform_user_data = client;
    }

    /* publish */
    client_options.publish_received_handler = s_on_publish_received;
    client_options.publish_received_handler_user_data = client;

    /* lifecycle events*/
    client_options.lifecycle_event_handler = s_lifecycle_event_callback;
    client_options.lifecycle_event_handler_user_data = client;

    /* termination */
    client_options.client_termination_handler = s_mqtt5_client_on_terminate;
    client_options.client_termination_handler_user_data = client;

    /* set up the new mqtt5 client */
    client->native = aws_mqtt5_client_new(allocator, &client_options);
    if (client->native == NULL) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;

done:
    aws_tls_connection_options_clean_up(&tls_options);
    if (user_properties_tmp) {
        aws_mem_release(aws_py_get_allocator(), user_properties_tmp);
    }
    if (will_user_properties_tmp) {
        aws_mem_release(aws_py_get_allocator(), will_user_properties_tmp);
    }
    PyBuffer_Release(&will_payload_stack);
    PyBuffer_Release(&will_correlation_data_stack);
    if (success) {
        return capsule;
    }
    Py_XDECREF(capsule);
    return NULL;
}

struct aws_mqtt5_client *aws_py_get_mqtt5_client(PyObject *mqtt5_client) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(mqtt5_client, s_capsule_name_mqtt5_client, "Client", mqtt5_client_binding);
}

/*******************************************************************************
 * Start
 ******************************************************************************/

PyObject *aws_py_mqtt5_client_start(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *impl_capsule;

    if (!PyArg_ParseTuple(args, "O", &impl_capsule)) {
        return NULL;
    }

    struct mqtt5_client_binding *client = PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt5_client);
    if (!client) {
        goto done;
    }

    if (aws_mqtt5_client_start(client->native)) {
        PyErr_SetAwsLastError();
        goto done;
    }
    success = true;

done:
    if (success) {
        Py_RETURN_NONE;
    }
    return NULL;
}

/*******************************************************************************
 * Stop
 ******************************************************************************/

PyObject *aws_py_mqtt5_client_stop(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *impl_capsule;

    PyObject *is_disconnect_packet_none_py;
    PyObject *reason_code_py;
    PyObject *session_expiry_interval_sec_py; /* optional uint32_t */
    struct aws_byte_cursor reason_string;     /* optional */
    PyObject *user_properties_py;             /* optional */
    struct aws_byte_cursor server_reference;  /* optional */

    if (!PyArg_ParseTuple(
            args,
            "OOOOz#Oz#",
            /* O */ &impl_capsule,
            /* O */ &is_disconnect_packet_none_py,
            /* O */ &reason_code_py,
            /* O */ &session_expiry_interval_sec_py,
            /* z */ &reason_string.ptr,
            /* # */ &reason_string.len,
            /* O */ &user_properties_py,
            /* z */ &server_reference.ptr,
            /* # */ &server_reference.len)) {
        return NULL;
    }

    struct mqtt5_client_binding *client = PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt5_client);
    if (!client) {
        return NULL;
    }
    struct aws_mqtt5_user_property *user_properties_tmp = NULL;

    /* stop can be called with a NULL disconnect_view */
    if (PyObject_IsTrue(is_disconnect_packet_none_py)) {
        if (aws_mqtt5_client_stop(client->native, NULL, NULL)) {
            PyErr_SetAwsLastError();
            goto done;
        }
        success = true;
        goto done;
    }

    struct aws_mqtt5_packet_disconnect_view disconnect_view;
    AWS_ZERO_STRUCT(disconnect_view);

    /* Fill out disconnect_view */
    disconnect_view.reason_code = PyObject_GetIntEnum(reason_code_py, AWS_PYOBJECT_KEY_REASON_CODE);
    if (PyErr_Occurred()) {
        goto done;
    }

    uint32_t session_expiry_interval_sec_tmp = 0;
    disconnect_view.session_expiry_interval_seconds = PyObject_GetAsOptionalUint32(
        session_expiry_interval_sec_py,
        AWS_PYOBJECT_KEY_DISCONNECT_PACKET,
        AWS_PYOBJECT_KEY_SESSION_EXPIRY_INTERVAL_SEC,
        &session_expiry_interval_sec_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    if (reason_string.ptr != NULL) {
        disconnect_view.reason_string = &reason_string;
    }

    user_properties_tmp =
        aws_get_optional_user_properties_from_PyObject(user_properties_py, &disconnect_view.user_property_count);
    if (PyErr_Occurred()) {
        goto done;
    }
    disconnect_view.user_properties = user_properties_tmp;

    if (server_reference.ptr != NULL) {
        disconnect_view.server_reference = &server_reference;
    }

    if (aws_mqtt5_client_stop(client->native, &disconnect_view, NULL)) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;
    goto done;

done:
    if (user_properties_tmp) {
        aws_mem_release(aws_py_get_allocator(), user_properties_tmp);
    }

    if (success) {
        Py_RETURN_NONE;
    }
    return NULL;
}

/*******************************************************************************
 * Publish
 ******************************************************************************/

struct publish_complete_userdata {
    PyObject *callback;
    enum aws_mqtt5_qos qos;
};

static void s_on_publish_complete_fn(
    enum aws_mqtt5_packet_type packet_type,
    const void *packet,
    int error_code,
    void *complete_ctx) {
    struct publish_complete_userdata *metadata = complete_ctx;
    assert(metadata);

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* These must be DECREF'd when function ends */
    PyObject *user_properties_list = NULL;
    PyObject *result = NULL;

    const struct aws_mqtt5_packet_puback_view *puback = NULL;
    enum aws_mqtt5_puback_reason_code reason_code = 0;
    const struct aws_byte_cursor *reason_string = NULL;
    size_t user_property_count = 0;

    if (packet_type == AWS_MQTT5_PT_PUBACK) {
        if (packet != NULL) {
            puback = packet;
            reason_code = puback->reason_code;
            reason_string = puback->reason_string;
            user_property_count = puback->user_property_count;

            user_properties_list = s_aws_set_user_properties_to_PyObject(puback->user_properties, user_property_count);
            if (PyErr_Occurred()) {
                PyErr_WriteUnraisable(PyErr_Occurred());
                goto cleanup;
            }
        }
    }

    result = PyObject_CallFunction(
        metadata->callback,
        "(iiis#O)",
        /* i */ (int)error_code,
        /* i */ (int)metadata->qos,
        /* i */ (int)reason_code,
        /* s */ reason_string ? reason_string->ptr : NULL,
        /* # */ reason_string ? reason_string->len : 0,
        /* O */ (user_property_count > 0 && !error_code) ? user_properties_list : Py_None);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
cleanup:
    Py_XDECREF(metadata->callback);
    Py_XDECREF(user_properties_list);
    Py_XDECREF(result);

    PyGILState_Release(state);

    aws_mem_release(aws_py_get_allocator(), metadata);
}

PyObject *aws_py_mqtt5_client_publish(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *impl_capsule;

    PyObject *qos_val_py;
    Py_buffer payload_stack; /* Py_buffers must be released after successful PyArg_ParseTuple() calls */
    PyObject *retain_py;
    struct aws_byte_cursor topic;
    PyObject *payload_format_py;                  /* optional enum */
    PyObject *message_expiry_interval_seconds_py; /* optional uint32_t */
    PyObject *topic_alias_py;                     /* optional uint16_t */
    struct aws_byte_cursor response_topic;        /* optional */
    Py_buffer correlation_data_stack;             /* optional */
    struct aws_byte_cursor content_type;          /* optional */
    PyObject *user_properties_py;                 /* optional */
    PyObject *puback_callback_fn_py;

    if (!PyArg_ParseTuple(
            args,
            "OOz*Oz#OOOz#z*z#OO",
            /* O */ &impl_capsule,
            /* O */ &qos_val_py,
            /* z* */ &payload_stack,
            /* O */ &retain_py,
            /* z */ &topic.ptr,
            /* # */ &topic.len,
            /* O */ &payload_format_py,
            /* O */ &message_expiry_interval_seconds_py,
            /* O */ &topic_alias_py,
            /* z */ &response_topic.ptr,
            /* # */ &response_topic.len,
            /* z* */ &correlation_data_stack,
            /* z */ &content_type.ptr,
            /* # */ &content_type.len,
            /* O */ &user_properties_py,
            /* O */ &puback_callback_fn_py)) {
        return NULL;
    }

    /* from hereon, we need to clean up if errors occur */
    struct aws_mqtt5_user_property *user_properties_tmp = NULL;

    struct mqtt5_client_binding *client = PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt5_client);
    if (!client) {
        goto done;
    }

    struct aws_mqtt5_packet_publish_view publish_view;
    AWS_ZERO_STRUCT(publish_view);

    publish_view.qos = PyObject_GetIntEnum(qos_val_py, AWS_PYOBJECT_KEY_QOS);
    if (PyErr_Occurred()) {
        goto done;
    }

    publish_view.payload = aws_byte_cursor_from_array(payload_stack.buf, payload_stack.len);

    publish_view.retain = PyObject_IsTrue(retain_py);

    publish_view.topic = topic;

    int payload_format_tmp = 0;
    enum aws_mqtt5_payload_format_indicator payload_format_enum_tmp;
    if (PyObject_GetAsOptionalIntEnum(
            payload_format_py,
            AWS_PYOBJECT_KEY_PUBLISH_PACKET,
            AWS_PYOBJECT_KEY_PAYLOAD_FORMAT_INDICATOR,
            &payload_format_tmp)) {
        payload_format_enum_tmp = (enum aws_mqtt5_payload_format_indicator)payload_format_tmp;
        publish_view.payload_format = &payload_format_enum_tmp;
    }
    if (PyErr_Occurred()) {
        goto done;
    }

    uint32_t message_expiry_interval_seconds_tmp = 0;
    publish_view.message_expiry_interval_seconds = PyObject_GetAsOptionalUint32(
        message_expiry_interval_seconds_py,
        AWS_PYOBJECT_KEY_PUBLISH_PACKET,
        AWS_PYOBJECT_KEY_MESSAGE_EXPIRY_INTERVAL_SEC,
        &message_expiry_interval_seconds_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    uint16_t topic_alias_tmp = 0;
    publish_view.topic_alias = PyObject_GetAsOptionalUint16(
        topic_alias_py, AWS_PYOBJECT_KEY_PUBLISH_PACKET, AWS_PYOBJECT_KEY_TOPIC_ALIAS, &topic_alias_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    if (response_topic.ptr) {
        publish_view.response_topic = &response_topic;
    }

    struct aws_byte_cursor correlation_data_tmp;
    if (correlation_data_stack.buf) {
        correlation_data_tmp = aws_byte_cursor_from_array(correlation_data_stack.buf, correlation_data_stack.len);
        publish_view.correlation_data = &correlation_data_tmp;
    }

    if (content_type.ptr) {
        publish_view.content_type = &content_type;
    }

    user_properties_tmp =
        aws_get_optional_user_properties_from_PyObject(user_properties_py, &publish_view.user_property_count);
    if (PyErr_Occurred()) {
        goto done;
    }
    publish_view.user_properties = user_properties_tmp;

    struct publish_complete_userdata *metadata = NULL;
    /* callback related must be cleaned up after this point */
    metadata = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct publish_complete_userdata));

    metadata->callback = puback_callback_fn_py;
    metadata->qos = PyObject_GetIntEnum(qos_val_py, AWS_PYOBJECT_KEY_QOS);
    Py_INCREF(metadata->callback);

    struct aws_mqtt5_publish_completion_options publish_completion_options = {
        .completion_callback = &s_on_publish_complete_fn, .completion_user_data = metadata};

    if (aws_mqtt5_client_publish(client->native, &publish_view, &publish_completion_options)) {
        PyErr_SetAwsLastError();
        goto publish_failed;
    }

    success = true;
    goto done;

publish_failed:
    Py_XDECREF(puback_callback_fn_py);
    aws_mem_release(aws_py_get_allocator(), metadata);

done:
    if (user_properties_tmp) {
        aws_mem_release(aws_py_get_allocator(), user_properties_tmp);
    }
    PyBuffer_Release(&payload_stack);
    PyBuffer_Release(&correlation_data_stack);
    if (success) {
        Py_RETURN_NONE;
    }
    return NULL;
}

/*******************************************************************************
 * Subscribe
 ******************************************************************************/

struct subscribe_complete_userdata {
    PyObject *callback;
};

static void s_on_subscribe_complete_fn(
    const struct aws_mqtt5_packet_suback_view *suback,
    int error_code,
    void *complete_ctx) {
    struct subscribe_complete_userdata *metadata = complete_ctx;
    assert(metadata);

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* These must be DECREF'd when function ends */
    PyObject *result = NULL;
    PyObject *reason_codes_list = NULL;
    PyObject *user_properties_list = NULL;
    size_t user_property_count = 0;
    size_t reason_codes_count = 0;

    if (suback != NULL) {
        user_property_count = suback->user_property_count;
        reason_codes_count = suback->reason_code_count;

        user_properties_list = s_aws_set_user_properties_to_PyObject(suback->user_properties, user_property_count);
        if (PyErr_Occurred()) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            goto cleanup;
        }

        /* Create list of (reason_code) tuples */
        reason_codes_list = PyList_New(reason_codes_count);
        if (!reason_codes_list) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            goto cleanup;
        }

        for (size_t i = 0; i < reason_codes_count; ++i) {
            PyList_SetItem(reason_codes_list, i, PyLong_FromLong(suback->reason_codes[i])); /* Steals a reference */
        }
    }

    result = PyObject_CallFunction(
        metadata->callback,
        "(iOs#O)",
        /* i */ (int)error_code,
        /* O */ (reason_codes_count > 0 && !error_code) ? reason_codes_list : Py_None,
        /* s */ (suback && suback->reason_string) ? suback->reason_string->ptr : NULL,
        /* # */ (suback && suback->reason_string) ? suback->reason_string->len : 0,
        /* O */ (user_property_count > 0 && !error_code) ? user_properties_list : Py_None);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
cleanup:
    Py_XDECREF(metadata->callback);
    Py_XDECREF(user_properties_list);
    Py_XDECREF(reason_codes_list);
    Py_XDECREF(result);

    PyGILState_Release(state);

    aws_mem_release(aws_py_get_allocator(), metadata);
}

/* Populates subscription_view_out from a PyObject user property.
 * PyErr_Occurred() must be called to check if anything went wrong after using this function. */
void aws_init_subscription_from_PyObject(PyObject *o, struct aws_mqtt5_subscription_view *subscription_view_out) {

    PyObject *attr_topic_filter = PyObject_GetAttrString(o, AWS_PYOBJECT_KEY_TOPIC_FILTER);
    if (!attr_topic_filter) {
        PyErr_Format(
            PyExc_AttributeError,
            "'%s.%s' attribute not found",
            AWS_PYOBJECT_KEY_SUBSCRIPTION,
            AWS_PYOBJECT_KEY_TOPIC_FILTER);
        return;
    }
    subscription_view_out->topic_filter = aws_byte_cursor_from_pyunicode(attr_topic_filter);
    Py_XDECREF(attr_topic_filter);
    if (PyErr_Occurred()) {
        return;
    }

    subscription_view_out->qos = PyObject_GetAttrAsIntEnum(o, AWS_PYOBJECT_KEY_SUBSCRIPTION, AWS_PYOBJECT_KEY_QOS);
    if (PyErr_Occurred()) {
        return;
    }

    subscription_view_out->no_local =
        PyObject_GetAttrAsBool(o, AWS_PYOBJECT_KEY_SUBSCRIPTION, AWS_PYOBJECT_KEY_NO_LOCAL);
    if (PyErr_Occurred()) {
        return;
    }

    subscription_view_out->retain_as_published =
        PyObject_GetAttrAsBool(o, AWS_PYOBJECT_KEY_SUBSCRIPTION, AWS_PYOBJECT_KEY_RETAIN_AS_PUBLISHED);
    if (PyErr_Occurred()) {
        return;
    }

    subscription_view_out->retain_handling_type =
        PyObject_GetAttrAsIntEnum(o, AWS_PYOBJECT_KEY_SUBSCRIPTION, AWS_PYOBJECT_KEY_RETAIN_HANDLING_TYPE);
    if (PyErr_Occurred()) {
        return;
    }
}

PyObject *aws_py_mqtt5_client_subscribe(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *impl_capsule;
    PyObject *subscriptions_py;
    PyObject *subscription_identifier_py; /* optional uint32_t */
    PyObject *user_properties_py;         /* optional */
    PyObject *suback_callback_fn_py;

    if (!PyArg_ParseTuple(
            args,
            "OOOOO",
            /* O */ &impl_capsule,
            /* O */ &subscriptions_py,
            /* O */ &subscription_identifier_py,
            /* O */ &user_properties_py,
            /* O */ &suback_callback_fn_py)) {
        return NULL;
    }

    struct mqtt5_client_binding *client = PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt5_client);
    if (!client) {
        return NULL;
    }

    struct aws_mqtt5_packet_subscribe_view subscribe_view;
    AWS_ZERO_STRUCT(subscribe_view);
    struct aws_mqtt5_user_property *user_properties_tmp = NULL;

    struct aws_array_list subscriptions_list;
    AWS_ZERO_STRUCT(subscriptions_list);

    if (!PySequence_Check(subscriptions_py)) {
        PyErr_Format(PyExc_TypeError, "'%s' argument must be of list or tuple", AWS_PYOBJECT_KEY_SUBSCRIPTIONS);
        goto done;
    }

    Py_ssize_t subscription_count = PySequence_Size(subscriptions_py);

    if (aws_array_list_init_dynamic(
            &subscriptions_list,
            aws_py_get_allocator(),
            subscription_count,
            sizeof(struct aws_mqtt5_subscription_view))) {
        PyErr_AwsLastError();
        goto done;
    }

    PyObject *subscription_py;
    for (Py_ssize_t i = 0; i < subscription_count; ++i) {
        struct aws_mqtt5_subscription_view subscription_out;
        AWS_ZERO_STRUCT(subscription_out);
        subscription_py = PySequence_GetItem(subscriptions_py, i);
        aws_init_subscription_from_PyObject(subscription_py, &subscription_out);
        if (PyErr_Occurred()) {
            Py_XDECREF(subscription_py);
            goto done;
        }
        aws_array_list_push_back(&subscriptions_list, &subscription_out);
        Py_XDECREF(subscription_py);
    }

    subscribe_view.subscription_count = (size_t)subscription_count;
    subscribe_view.subscriptions = subscriptions_list.data;

    uint32_t subscription_identifier_tmp = 0;
    subscribe_view.subscription_identifier = PyObject_GetAsOptionalUint32(
        subscription_identifier_py,
        AWS_PYOBJECT_KEY_SUBSCRIBE_PACKET,
        AWS_PYOBJECT_KEY_SUBSCRIPTION_IDENTIFIER,
        &subscription_identifier_tmp);
    if (PyErr_Occurred()) {
        goto done;
    }

    user_properties_tmp =
        aws_get_optional_user_properties_from_PyObject(user_properties_py, &subscribe_view.user_property_count);
    if (PyErr_Occurred()) {
        goto done;
    }
    subscribe_view.user_properties = user_properties_tmp;

    struct subscribe_complete_userdata *metadata = NULL;
    /* callback related must be cleaned up after this point */
    metadata = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct subscribe_complete_userdata));

    metadata->callback = suback_callback_fn_py;
    Py_INCREF(metadata->callback);

    struct aws_mqtt5_subscribe_completion_options subscribe_completion_options = {
        .completion_callback = &s_on_subscribe_complete_fn, .completion_user_data = metadata};

    if (aws_mqtt5_client_subscribe(client->native, &subscribe_view, &subscribe_completion_options)) {
        PyErr_SetAwsLastError();
        goto subscribe_failed;
    }

    success = true;
    goto done;

subscribe_failed:
    Py_XDECREF(suback_callback_fn_py);
    aws_mem_release(aws_py_get_allocator(), metadata);

done:
    if (user_properties_tmp) {
        aws_mem_release(aws_py_get_allocator(), user_properties_tmp);
    }
    aws_array_list_clean_up(&subscriptions_list);
    if (success) {
        Py_RETURN_NONE;
    }
    return NULL;
}

/*******************************************************************************
 * Unsubscribe
 ******************************************************************************/

struct unsubscribe_complete_userdata {
    PyObject *callback;
};

static void s_on_unsubscribe_complete_fn(
    const struct aws_mqtt5_packet_unsuback_view *unsuback,
    int error_code,
    void *complete_ctx) {
    struct unsubscribe_complete_userdata *metadata = complete_ctx;
    assert(metadata);

    /* These must be DECREF'd when function ends */
    PyObject *result = NULL;
    PyObject *reason_codes_list = NULL;
    PyObject *user_properties_list = NULL;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    size_t user_property_count = 0;
    size_t reason_codes_count = 0;

    if (unsuback != NULL) {
        user_property_count = unsuback->user_property_count;
        reason_codes_count = unsuback->reason_code_count;

        user_properties_list = s_aws_set_user_properties_to_PyObject(unsuback->user_properties, user_property_count);
        if (PyErr_Occurred()) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            goto cleanup;
        }

        /* Create list of (reason_code) tuples */
        reason_codes_list = PyList_New(reason_codes_count);
        if (!reason_codes_list) {
            error_code = aws_py_translate_py_error();
            goto cleanup;
        }

        for (size_t i = 0; i < reason_codes_count; ++i) {
            PyList_SetItem(reason_codes_list, i, PyLong_FromLong(unsuback->reason_codes[i])); /* Steals a reference */
        }
    }

    result = PyObject_CallFunction(
        metadata->callback,
        "(iOs#O)",
        /* i */ (int)error_code,
        /* O */ (reason_codes_count > 0 && !error_code) ? reason_codes_list : Py_None,
        /* s */ (unsuback && unsuback->reason_string) ? unsuback->reason_string->ptr : NULL,
        /* # */ (unsuback && unsuback->reason_string) ? unsuback->reason_string->len : 0,
        /* O */ (user_property_count > 0 && !error_code) ? user_properties_list : Py_None);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
cleanup:
    Py_XDECREF(metadata->callback);
    Py_XDECREF(user_properties_list);
    Py_XDECREF(reason_codes_list);
    Py_XDECREF(result);

    PyGILState_Release(state);

    aws_mem_release(aws_py_get_allocator(), metadata);
}

PyObject *aws_py_mqtt5_client_unsubscribe(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *impl_capsule;
    PyObject *topic_filters_py;
    PyObject *user_properties_py; /* optional */
    PyObject *unsuback_callback_fn_py;

    if (!PyArg_ParseTuple(
            args,
            "OOOO",
            /* O */ &impl_capsule,
            /* O */ &topic_filters_py,
            /* O */ &user_properties_py,
            /* O */ &unsuback_callback_fn_py)) {
        return NULL;
    }

    struct mqtt5_client_binding *client = PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt5_client);
    if (!client) {
        return NULL;
    }

    struct aws_mqtt5_packet_unsubscribe_view unsubscribe_view;
    AWS_ZERO_STRUCT(unsubscribe_view);
    struct aws_mqtt5_user_property *user_properties_tmp = NULL;

    struct aws_array_list topic_filters_list;
    AWS_ZERO_STRUCT(topic_filters_list);

    if (!PySequence_Check(topic_filters_py)) {
        PyErr_Format(PyExc_TypeError, "'%s' argument must be of list or tuple", AWS_PYOBJECT_KEY_TOPIC_FILTERS);
        goto done;
    }

    Py_ssize_t topic_filters_count = PySequence_Size(topic_filters_py);

    if (aws_array_list_init_dynamic(
            &topic_filters_list, aws_py_get_allocator(), topic_filters_count, sizeof(struct aws_byte_cursor))) {
        PyErr_AwsLastError();
        goto done;
    }

    PyObject *topic_filter_py;
    for (Py_ssize_t i = 0; i < topic_filters_count; ++i) {
        struct aws_byte_cursor topic_filter_to_add;
        AWS_ZERO_STRUCT(topic_filter_to_add);
        topic_filter_py = PySequence_GetItem(topic_filters_py, i);
        topic_filter_to_add = aws_byte_cursor_from_pyunicode(topic_filter_py);
        if (!topic_filter_to_add.ptr) {
            PyErr_Format(
                PyExc_TypeError,
                "'%s.%s' at index %zu is not a valid string",
                AWS_PYOBJECT_KEY_UNSUBSCRIBE_PACKET,
                AWS_PYOBJECT_KEY_TOPIC_FILTERS,
                i);
            Py_XDECREF(topic_filter_py);
            goto done;
        }
        aws_array_list_push_back(&topic_filters_list, &topic_filter_to_add);
        Py_XDECREF(topic_filter_py);
    }

    unsubscribe_view.topic_filter_count = (size_t)topic_filters_count;
    unsubscribe_view.topic_filters = topic_filters_list.data;

    user_properties_tmp =
        aws_get_optional_user_properties_from_PyObject(user_properties_py, &unsubscribe_view.user_property_count);
    if (PyErr_Occurred()) {
        goto done;
    }
    unsubscribe_view.user_properties = user_properties_tmp;

    struct unsubscribe_complete_userdata *metadata = NULL;
    /* callback related must be cleaned up after this point */
    metadata = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct unsubscribe_complete_userdata));

    metadata->callback = unsuback_callback_fn_py;
    Py_INCREF(metadata->callback);

    struct aws_mqtt5_unsubscribe_completion_options unsubscribe_completion_options = {
        .completion_callback = &s_on_unsubscribe_complete_fn, .completion_user_data = metadata};

    if (aws_mqtt5_client_unsubscribe(client->native, &unsubscribe_view, &unsubscribe_completion_options)) {
        PyErr_SetAwsLastError();
        goto unsubscribe_failed;
    }

    success = true;
    goto done;

unsubscribe_failed:
    Py_XDECREF(unsuback_callback_fn_py);
    aws_mem_release(aws_py_get_allocator(), metadata);

done:
    if (user_properties_tmp) {
        aws_mem_release(aws_py_get_allocator(), user_properties_tmp);
    }
    aws_array_list_clean_up(&topic_filters_list);

    if (success) {
        Py_RETURN_NONE;
    }
    return NULL;
}

/*******************************************************************************
 * Get Stats
 ******************************************************************************/

struct get_stats_complete_userdata {
    PyObject *callback;
};

PyObject *aws_py_mqtt5_client_get_stats(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *impl_capsule;

    if (!PyArg_ParseTuple(args, "O", &impl_capsule)) {
        return NULL;
    }

    struct mqtt5_client_binding *client = PyCapsule_GetPointer(impl_capsule, s_capsule_name_mqtt5_client);
    if (!client) {
        return NULL;
    }

    /* These must be DECREF'd when function ends on error */
    PyObject *result = NULL;

    struct aws_mqtt5_client_operation_statistics stats;
    AWS_ZERO_STRUCT(stats);

    aws_mqtt5_client_get_stats(client->native, &stats);

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
