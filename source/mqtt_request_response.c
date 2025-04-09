/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "mqtt_request_response.h"

#include "mqtt5_client.h"
#include "mqtt_client_connection.h"

#include "aws/mqtt/request-response/request_response_client.h"

static const char *s_capsule_name_mqtt_request_response_client = "aws_mqtt_request_response_client";

static const char *AWS_PYOBJECT_KEY_REQUEST_RESPONSE_CLIENT_OPTIONS = "RequestResponseClientOptions";
static const char *AWS_PYOBJECT_KEY_MAX_REQUEST_RESPONSE_SUBSCRIPTIONS = "max_request_response_subscriptions";
static const char *AWS_PYOBJECT_KEY_MAX_STREAMING_SUBSCRIPTIONS = "max_streaming_subscriptions";
static const char *AWS_PYOBJECT_KEY_OPERATION_TIMEOUT_IN_SECONDS = "operation_timeout_in_seconds";

struct mqtt_request_response_client_binding {
    struct aws_mqtt_request_response_client *native;
};

static void s_mqtt_request_response_python_client_destructor(PyObject *client_capsule) {
    struct mqtt_request_response_client_binding *client_binding =
        PyCapsule_GetPointer(client_capsule, s_capsule_name_mqtt_request_response_client);
    assert(client_binding);

    client_binding->native = aws_mqtt_request_response_client_release(client_binding->native);

    aws_mem_release(aws_py_get_allocator(), client_binding);
}

/*
 * Returns success as true/false.  If not successful, a python error will be set, so the caller does not need to check
 */
static bool s_init_mqtt_request_response_client_options(
    struct aws_mqtt_request_response_client_options *client_options,
    PyObject *client_options_py) {
    AWS_ZERO_STRUCT(*client_options);

    uint32_t max_request_response_subscriptions = PyObject_GetAttrAsUint32(
        client_options_py,
        AWS_PYOBJECT_KEY_REQUEST_RESPONSE_CLIENT_OPTIONS,
        AWS_PYOBJECT_KEY_MAX_REQUEST_RESPONSE_SUBSCRIPTIONS);
    if (PyErr_Occurred()) {
        PyErr_Format(PyErr_Occurred(), "Cannot convert max_request_response_subscriptions to a C uint32");
        return false;
    }

    uint32_t max_streaming_subscriptions = PyObject_GetAttrAsUint32(
        client_options_py,
        AWS_PYOBJECT_KEY_REQUEST_RESPONSE_CLIENT_OPTIONS,
        AWS_PYOBJECT_KEY_MAX_STREAMING_SUBSCRIPTIONS);
    if (PyErr_Occurred()) {
        PyErr_Format(PyErr_Occurred(), "Cannot convert max_streaming_subscriptions to a C uint32");
        return false;
    }

    uint32_t timeout_in_seconds = PyObject_GetAttrAsUint32(
        client_options_py,
        AWS_PYOBJECT_KEY_REQUEST_RESPONSE_CLIENT_OPTIONS,
        AWS_PYOBJECT_KEY_OPERATION_TIMEOUT_IN_SECONDS);
    if (PyErr_Occurred()) {
        PyErr_Format(PyErr_Occurred(), "Cannot convert operation_timeout_in_seconds to a C uint32_t");
        return false;
    }

    client_options->max_request_response_subscriptions = (size_t)max_request_response_subscriptions;
    client_options->max_streaming_subscriptions = (size_t)max_streaming_subscriptions;
    client_options->operation_timeout_seconds = (uint32_t)timeout_in_seconds;

    return true;
}

PyObject *aws_py_mqtt_request_response_client_new_from_5(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *mqtt5_client_py = NULL;
    PyObject *client_options_py = NULL;

    if (!PyArg_ParseTuple(
            args,
            "OO",
            /* O */ &mqtt5_client_py,
            /* O */ &client_options_py)) {
        return NULL;
    }

    struct aws_mqtt5_client *protocol_client = aws_py_get_mqtt5_client(mqtt5_client_py);
    if (protocol_client == NULL) {
        return NULL;
    }

    struct aws_mqtt_request_response_client_options client_options;
    if (!s_init_mqtt_request_response_client_options(&client_options, client_options_py)) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_mqtt_request_response_client *rr_client =
        aws_mqtt_request_response_client_new_from_mqtt5_client(allocator, protocol_client, &client_options);
    if (rr_client == NULL) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    struct mqtt_request_response_client_binding *client_binding =
        aws_mem_calloc(allocator, 1, sizeof(struct mqtt_request_response_client_binding));
    // Python object that wraps a c struct and a function to call when its reference goes to zero
    PyObject *capsule = PyCapsule_New(
        client_binding, s_capsule_name_mqtt_request_response_client, s_mqtt_request_response_python_client_destructor);
    if (!capsule) {
        aws_mem_release(allocator, client_binding);
        aws_mqtt_request_response_client_release(rr_client);
        return NULL;
    }

    client_binding->native = rr_client;

    return capsule;
}

PyObject *aws_py_mqtt_request_response_client_new_from_311(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *mqtt_connection_py = NULL;
    PyObject *client_options_py = NULL;

    if (!PyArg_ParseTuple(
            args,
            "OO",
            /* O */ &mqtt_connection_py,
            /* O */ &client_options_py)) {
        return NULL;
    }

    struct aws_mqtt_client_connection *protocol_client = aws_py_get_mqtt_client_connection(mqtt_connection_py);
    if (protocol_client == NULL) {
        return NULL;
    }

    struct aws_mqtt_request_response_client_options client_options;
    if (!s_init_mqtt_request_response_client_options(&client_options, client_options_py)) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_mqtt_request_response_client *rr_client =
        aws_mqtt_request_response_client_new_from_mqtt311_client(allocator, protocol_client, &client_options);
    if (rr_client == NULL) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    struct mqtt_request_response_client_binding *client_binding =
        aws_mem_calloc(allocator, 1, sizeof(struct mqtt_request_response_client_binding));
    // Python object that wraps a c struct and a function to call when its reference goes to zero
    PyObject *capsule = PyCapsule_New(
        client_binding, s_capsule_name_mqtt_request_response_client, s_mqtt_request_response_python_client_destructor);
    if (!capsule) {
        aws_mem_release(allocator, client_binding);
        aws_mqtt_request_response_client_release(rr_client);
        return NULL;
    }

    client_binding->native = rr_client;

    return capsule;
}

struct aws_mqtt_request_response_client *aws_py_get_mqtt_request_response_client(
    PyObject *mqtt_request_response_client) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        mqtt_request_response_client,
        s_capsule_name_mqtt_request_response_client,
        "Client",
        mqtt_request_response_client_binding);
}