/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "mqtt5_listener.h"
#include "http.h"
#include "io.h"
#include "mqtt5_client.h"

#include <aws/http/proxy.h>
#include <aws/io/socket.h>
#include <aws/io/tls_channel_handler.h>
#include <aws/mqtt/v5/mqtt5_client.h>
#include <aws/mqtt/v5/mqtt5_listener.h>
#include <aws/mqtt/v5/mqtt5_types.h>

#include <stdio.h>

static const char *s_capsule_name_mqtt5_listener = "aws_mqtt5_listener";

struct mqtt5_listener_binding {
    struct aws_mqtt5_listener *native;
    PyObject *client_py;
    PyObject *listener_core;
};

/* Called on either failed client creation or by the client upon normal client termination */
static void s_mqtt5_listener_on_terminate(void *user_data) {
    struct mqtt5_listener_binding *listener = user_data;
    aws_mem_release(aws_py_get_allocator(), listener);
}

/* Called when capsule's refcount hits 0 */
static void s_mqtt5_python_listener_destructor(PyObject *listener_capsule) {
    struct mqtt5_listener_binding *listener = PyCapsule_GetPointer(listener_capsule, s_capsule_name_mqtt5_listener);
    assert(listener);

    Py_XDECREF(listener->client_py);
    Py_XDECREF(listener->listener_core);

    if (listener->native != NULL) {
        /* If client is not NULL, it can be shutdown and cleaned normally */
        aws_mqtt5_listener_release(listener->native);
        listener->native = NULL;
    } else {
        /* A failed client that must be cleaned up directly */
        s_mqtt5_listener_on_terminate(listener);
    }
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
        PyList_SET_ITEM(user_properties_list, i, tuple); /* Steals reference to tuple */
    }
    return user_properties_list;
}

/*******************************************************************************
 * Publish Handler
 ******************************************************************************/

static bool s_on_publish_received(const struct aws_mqtt5_packet_publish_view *publish_packet, void *user_data) {

    bool success = false;
    if (!user_data) {
        return false;
    }
    struct mqtt5_listener_binding *listener = user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return false; /* Python has shut down. Nothing matters anymore, but don't crash */
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
        PyList_SET_ITEM(
            subscription_identifier_list, i, PyLong_FromLongLong(publish_packet->subscription_identifiers[i]));
    }

    user_properties_list = s_aws_set_user_properties_to_PyObject(publish_packet->user_properties, user_property_count);
    if (PyErr_Occurred()) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto cleanup;
    }

    result = PyObject_CallMethod(
        listener->listener_core,
        "_on_listener_publish",
        "(y#iOs#OiOIOHs#z#Os#O)",
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
        (unsigned int)(publish_packet->message_expiry_interval_seconds ? *publish_packet->message_expiry_interval_seconds : 0),
        /* O */ publish_packet->topic_alias ? Py_True : Py_False,
        /* H */ (unsigned short)(publish_packet->topic_alias ? *publish_packet->topic_alias : 0),
        /* s */ publish_packet->response_topic ? publish_packet->response_topic->ptr : NULL,
        /* # */ publish_packet->response_topic ? publish_packet->response_topic->len : 0,
        /* z */ publish_packet->correlation_data ? publish_packet->correlation_data->ptr : NULL,
        /* # */ publish_packet->correlation_data ? publish_packet->correlation_data->len : 0,
        /* O */ subscription_identifier_count > 0 ? subscription_identifier_list : Py_None,
        /* s */ publish_packet->content_type ? publish_packet->content_type->ptr : NULL,
        /* # */ publish_packet->content_type ? publish_packet->content_type->len : 0,
        /* O */ user_property_count > 0 ? user_properties_list : Py_None);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto cleanup;
    }

    success = PyObject_IsTrue(result);

cleanup:
    Py_XDECREF(result);
    Py_XDECREF(subscription_identifier_list);
    Py_XDECREF(user_properties_list);
    PyGILState_Release(state);
    return success;
}

/*******************************************************************************
 * Lifecycle Event Handler
 ******************************************************************************/

static void s_lifecycle_event_stopped(struct mqtt5_listener_binding *listener) {
    if (!listener || !listener->listener_core) {
        return;
    }

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(listener->listener_core, "_on_lifecycle_stopped", NULL);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_XDECREF(result);

    PyGILState_Release(state);
}

static void s_lifecycle_event_attempting_connect(struct mqtt5_listener_binding *listener) {
    if (!listener || !listener->listener_core) {
        return;
    }

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(listener->listener_core, "_on_lifecycle_attempting_connect", NULL);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_XDECREF(result);

    PyGILState_Release(state);
}

static void s_lifecycle_event_connection_success(
    struct mqtt5_listener_binding *listener,
    const struct aws_mqtt5_packet_connack_view *connack,
    const struct aws_mqtt5_negotiated_settings *settings) {
    if (!listener || !listener->listener_core) {
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
        listener->listener_core,
        "_on_lifecycle_connection_success",
        "(OiOIOHOiOOOIs#s#OOOOOOOOHs#s#iIHIHHHOOOOO)",
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
        /* O */ settings->rejoined_session ? Py_True : Py_False);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
cleanup:
    Py_XDECREF(result);
    Py_XDECREF(user_properties_list);

    PyGILState_Release(state);
}

static void s_lifecycle_event_connection_failure(
    struct mqtt5_listener_binding *listener,
    const struct aws_mqtt5_packet_connack_view *connack,
    int error_code) {
    if (!listener || !listener->listener_core) {
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
        listener->listener_core,
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
    struct mqtt5_listener_binding *listener,
    const struct aws_mqtt5_packet_disconnect_view *disconnect,
    int error_code) {
    if (!listener || !listener->listener_core) {
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
        listener->listener_core,
        "_on_lifecycle_disconnection",
        "(iOiOIs#Os#)",
        /* i */ (int)error_code,
        /* O */ disconnect ? Py_True : Py_False,
        /* i */ (int)(disconnect ? disconnect->reason_code : 0),
        /* O */ (disconnect && disconnect->session_expiry_interval_seconds) ? Py_True : Py_False,
        /* I */
        (unsigned int)((disconnect && disconnect->session_expiry_interval_seconds) ? *disconnect->session_expiry_interval_seconds : 0),
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
 * Listener Init
 ******************************************************************************/

PyObject *aws_py_mqtt5_listener_new(PyObject *self, PyObject *args) {
    (void)self;
    bool success = false;

    PyObject *self_py;
    PyObject *client_py;

    PyObject *listener_core_py;

    if (!PyArg_ParseTuple(
            args,
            "OO",
            /* O */
            &client_py,
            /* O */
            &listener_core_py)) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct mqtt5_listener_binding *listener = aws_mem_calloc(allocator, 1, sizeof(struct mqtt5_listener_binding));
    // Python object that wraps a c struct and a function to call when its reference goes to zero
    PyObject *capsule = PyCapsule_New(listener, s_capsule_name_mqtt5_listener, s_mqtt5_python_listener_destructor);
    if (!capsule) {
        aws_mem_release(allocator, listener);
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */
    struct aws_mqtt5_listener_config listener_options;
    AWS_ZERO_STRUCT(listener_options);

    /* CALLBACKS */

    Py_INCREF(listener_core_py);
    listener->listener_core = listener_core_py;
    Py_INCREF(client_py);
    listener->client_py = client_py;

    /* publish */
    listener_options.listener_callbacks.listener_publish_received_handler = s_on_publish_received;
    listener_options.listener_callbacks.listener_publish_received_handler_user_data = listener;

    /* lifecycle events*/
    listener_options.listener_callbacks.lifecycle_event_handler = s_lifecycle_event_callback;
    listener_options.listener_callbacks.lifecycle_event_handler_user_data = listener;

    /* termination */
    listener_options.termination_callback = s_mqtt5_listener_on_terminate;
    listener_options.termination_callback_user_data = listener;

    /*client*/
    listener_options.client = aws_py_get_mqtt5_client(client_py);

    /* set up the new mqtt5 client */
    listener->native = aws_mqtt5_listener_new(allocator, &listener_options);
    if (listener->native == NULL) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;

done:
    if (success) {
        return capsule;
    }
    Py_XDECREF(capsule);
    return NULL;
}

struct aws_mqtt5_listener *aws_py_get_mqtt5_listener(PyObject *mqtt5_listener) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        mqtt5_listener, s_capsule_name_mqtt5_listener, "Listener", mqtt5_listener_binding);
}
