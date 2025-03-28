/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "mqtt_request_response_client.h"

#include "mqtt5_client.h"
#include "mqtt_client_connection.h"

static const char *s_capsule_name_mqtt_request_response_client = "aws_mqtt_request_response_client";

static const char *AWS_PYOBJECT_KEY_REQUEST_RESPONSE_CLIENT_OPTIONS = "RequestResponseClientOptions";
static const char *AWS_PYOBJECT_KEY_MAX_REQUEST_RESPONSE_SUBSCRIPTIONS = "max_request_response_subscriptions";
static const char *AWS_PYOBJECT_KEY_MAX_STREAMING_SUBSCRIPTIONS = "max_streaming_subscriptions";
static const char *AWS_PYOBJECT_KEY_OPERATION_TIMEOUT_IN_SECONDS = "operation_timeout_in_seconds";
static const char *AWS_PYOBJECT_KEY_TOPIC = "topic";
static const char *AWS_PYOBJECT_KEY_CORRELATION_TOKEN_JSON_PATH = "correlation_token_json_path";

struct mqtt_request_response_client_binding {
    struct aws_mqtt_request_response_client *native;
};

static void s_mqtt_request_response_python_client_destructor(PyObject *client_capsule) {
    struct mqtt_request_response_client_binding *client_binding =
        PyCapsule_GetPointer(client_capsule, s_capsule_name_mqtt_request_response_client);
    assert(client_binding);

    client_binding->native = aws_mqtt_request_response_client_release(client_binding->native);
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

static void s_cleanup_subscription_topic_filters(struct aws_array_list *subscription_topic_filters) {
    size_t filter_count = aws_array_list_length(subscription_topic_filters);
    for (size_t i = 0; i < filter_count; ++i) {
        struct aws_byte_buf filter_buffer;
        aws_array_list_get_at(subscription_topic_filters, &filter_buffer, i);

        aws_byte_buf_clean_up(&filter_buffer);
    }

    aws_array_list_clean_up(subscription_topic_filters);
}

static bool s_init_subscription_topic_filters(struct aws_array_list *subscription_topic_filters, PyObject *subscription_topic_filters_py) {
    AWS_ZERO_STRUCT(*subscription_topic_filters);

     if (!PySequence_Check(subscription_topic_filters_py)) {
        PyErr_Format(PyExc_TypeError, "subscription_topic_filters must be a sequence type");
        return false;
    }

    Py_ssize_t filter_count = PySequence_Size(subscription_topic_filters_py);
    if (filter_count <= 0) {
        return false;
    }

    bool success = false;
    struct aws_allocator *allocator = aws_py_get_allocator();
    aws_array_list_init_dynamic(subscription_topic_filters, allocator, (size_t)filter_count, sizeof(struct aws_byte_buf));

    for (size_t i = 0; i < (size_t)filter_count; ++i) {
        PyObject *entry_py = PySequence_GetItem(subscription_topic_filters_py, i);
        if (entry_py == NULL) {
            goto done;
        }

        struct aws_byte_cursor topic_filter_cursor = aws_byte_cursor_from_pyunicode(entry_py);

        struct aws_byte_buf topic_filter;
        aws_byte_buf_init_copy_from_cursor(&topic_filter, allocator, topic_filter_cursor);

        aws_array_list_push_back(subscription_topic_filters, &topic_filter);

        Py_XDECREF(entry_py);
    }

    success = true;

  done:

    if (!success) {
        s_cleanup_subscription_topic_filters(subscription_topic_filters);
        AWS_ZERO_STRUCT(*subscription_topic_filters);
    }

    return success;
}

struct aws_request_response_path {
    struct aws_byte_buf topic;
    struct aws_byte_buf correlation_token_json_path;
};

static void s_cleanup_response_paths(struct aws_array_list *response_paths) {
    size_t path_count = aws_array_list_length(response_paths);
    for (size_t i = 0; i < path_count; ++i) {
        struct aws_request_response_path response_path;
        aws_array_list_get_at(response_paths, &response_path, i);

        aws_byte_buf_clean_up(&response_path.topic);
        aws_byte_buf_clean_up(&response_path.correlation_token_json_path);
    }

    aws_array_list_clean_up(response_paths);
}

static bool s_init_response_paths(struct aws_array_list *response_paths, PyObject *response_paths_py) {
    AWS_ZERO_STRUCT(*response_paths);

     if (!PySequence_Check(response_paths_py)) {
        PyErr_Format(PyExc_TypeError, "response_paths must be a sequence type");
        return false;
    }

    Py_ssize_t path_count = PySequence_Size(response_paths_py);
    if (path_count <= 0) {
        return false;
    }

    bool success = false;
    struct aws_allocator *allocator = aws_py_get_allocator();
    aws_array_list_init_dynamic(response_paths, allocator, (size_t)path_count, sizeof(struct aws_request_response_path));

    for (size_t i = 0; i < (size_t)path_count; ++i) {
        PyObject *entry_py = PySequence_GetItem(subscription_topic_filters_py, i);
        if (entry_py == NULL) {
            goto done;
        }

        bool should_continue = true;
        PyObject *topic_py = PyObject_GetAttrString(entry_py, AWS_PYOBJECT_KEY_TOPIC);
        PyObject *correlation_token_json_path_py = PyObject_GetAttrString(entry_py, AWS_PYOBJECT_KEY_CORRELATION_TOKEN_JSON_PATH);

        if (topic_py != NULL && correlation_token_json_path_py != NULL) {
            struct aws_byte_cursor topic_cursor = aws_byte_cursor_from_pyunicode(topic_py);
            struct aws_byte_cursor correlation_token_json_path_cursor = aws_byte_cursor_from_pyunicode(correlation_token_json_path_py);

            struct aws_request_response_path response_path;
            aws_byte_buf_init_copy_from_cursor(&response_path.topic, allocator, topic_cursor);
            aws_byte_buf_init_copy_from_cursor(&response_path.correlation_token_json_path, allocator, correlation_token_json_path_cursor);

            aws_array_list_push_back(response_paths, &response_path);
        } else {
            PyErr_Format(PyExc_AttributeError, "invalid response path");
            should_continue = false;
        }

        Py_XDECREF(topic_py);
        Py_XDECREF(correlation_token_json_path_py);
        Py_XDECREF(entry_py);

        if (!should_continue) {
            goto done;
        }
    }

    success = true;

  done:

    if (!success) {
        s_cleanup_response_paths(response_paths);
        AWS_ZERO_STRUCT(*response_paths);
    }

    return success;
}

struct aws_mqtt_make_request_binding {
    PyObject *on_request_complete_callback;
};

static struct aws_mqtt_make_request_binding *s_aws_mqtt_make_request_binding_new(PyObject *on_request_complete_callable_py) {
    struct aws_mqtt_make_request_binding *binding = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct aws_mqtt_make_request_binding));

    binding->on_request_complete_callback = on_request_complete_callable_py;
    Py_XINCREF(binding->on_request_complete_callback);

    return binding;
}

static void s_aws_mqtt_make_request_binding_destroy(struct aws_mqtt_make_request_binding *binding) {
    if (binding == NULL) {
        return;
    }

    Py_XDECREF(binding->on_request_complete_callback);

    aws_mem_release(aws_py_get_allocator(), binding);
}

static void s_complete_mqtt_request(struct aws_mqtt_make_request_binding *request_binding, int error_code, const struct aws_byte_cursor *response_topic,
    const struct aws_byte_cursor *payload) {

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return;
    }

   PyObject *result = PyObject_CallFunction(
        request_binding->on_request_complete_callback,
        "(is#y#)",
        /* i */ (int)error_code,
        /* s */ response_topic ? response_topic->ptr : NULL,
        /* # */ response_topic ? response_topic->len : 0,
        /* y */ payload ? payload->ptr : NULL,
        /* # */ payload ? payload->len : 0);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

done:

    Py_XDECREF(result);
    PyGILState_Release(state);
}

static void s_on_mqtt_request_complete(
    const struct aws_byte_cursor *response_topic,
    const struct aws_byte_cursor *payload,
    int error_code,
    void *user_data) {

    struct aws_mqtt_make_request_binding *request_binding = user_data;

    s_complete_mqtt_request(request_binding, error_code, response_topic, payload);

    s_aws_mqtt_make_request_binding_destroy(request_binding);
}

PyObject *aws_py_mqtt_request_response_client_make_request(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *client_capsule_py;
    PyObject *subscription_topic_filters_py;
    PyObject *response_paths_py;
    struct aws_byte_cursor publish_topic;
    struct aws_byte_cursor payload;
    struct aws_byte_cursor correlation_token;
    PyObject *on_request_complete_callable_py;

    if (!PyArg_ParseTuple(
            args,
            "OOOs#y#z#O",
            /* O */ &client_capsule_py,
            /* O */ &subscription_topic_filters_py,
            /* O */ &response_paths_py,
            /* s */ &publish_topic.ptr,
            /* # */ &publish_topic.len,
            /* y */ &payload.ptr,
            /* # */ &payload.len,
            /* z */ &correlation_token.ptr,
            /* # */ &correlation_token.len,
            /* O */ &on_request_complete_callable_py)) {
        return NULL;
    }

    struct mqtt_request_response_client_binding *client_binding = PyCapsule_GetPointer(client_capsule_py, s_capsule_name_mqtt_request_response_client);
    if (!client_binding) {
        return NULL;
    }

    PyObject *result_py = NULL;
    struct aws_mqtt_make_request_binding *request_binding = s_aws_mqtt_make_request_binding_new(on_request_complete_callable_py);

    struct aws_array_list subscription_topic_filters; // array_list<aws_byte_buf>
    AWS_ZERO_STRUCT(subscription_topic_filters);

    struct aws_array_list response_paths; // array_list<aws_request_response_path>
    AWS_ZERO_STRUCT(response_paths);

    if (!s_init_subscription_topic_filters(&subscription_topic_filters, subscription_topic_filters_py)) {
        goto done;
    }

    if (!s_init_response_paths(&response_paths, response_paths_py)) {
        goto done;
    }

    size_t subscription_count = aws_array_list_length(&subscription_topic_filters);
    struct aws_byte_cursor subscription_topic_filter_cursors[subscription_count];
    for (size_t i = 0; i < subscription_count; ++i) {
        struct aws_byte_buf topic_filter;
        aws_array_list_get_at(&subscription_topic_filters, &topic_filter, i);

        subscription_topic_filter_cursors[i] = aws_byte_cursor_from_buf(&topic_filter);
    }

    size_t response_path_count = aws_array_list_length(&response_paths);
    struct aws_mqtt_request_operation_response_path response_path_values[response_path_count];
    for (size_t i = 0; i < subscription_count; ++i) {
        struct aws_request_response_path response_path;
        aws_array_list_get_at(&response_paths, &response_path, i);

        response_path_values[i].topic = aws_byte_cursor_from_buf(&response_path.topic);
        response_path_values[i].correlation_token_json_path = aws_byte_cursor_from_buf(&response_path.correlation_token_json_path);
    }

    struct aws_mqtt_request_operation_options request_options = {
        .subscription_topic_filters = subscription_topic_filter_cursors,
        .subscription_topic_filter_count = subscription_count,
        .response_paths = response_path_values,
        .response_path_count = response_path_count,
        .publish_topic = publish_topic,
        .serialized_request = payload,
        .correlation_token = correlation_token,
        .completion_callback = s_on_mqtt_request_complete,
        .user_data = request_binding,
    };

    if (aws_mqtt_request_response_client_submit_request(client_binding->native, &request_options)) {
        s_complete_mqtt_request(request_binding, aws_last_error(), NULL, NULL);
        goto done;
    }

    result_py = Py_None;

done:

    s_cleanup_subscription_topic_filters(&subscription_topic_filters);
    s_cleanup_response_paths(&response_paths);
    if (result_py == NULL) {
        s_aws_mqtt_make_request_binding_destroy(request_binding);
    }

    return result_py;
}

struct aws_mqtt_request_response_client *aws_py_get_mqtt_request_response_client(
    PyObject *mqtt_request_response_client) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        mqtt_request_response_client,
        s_capsule_name_mqtt_request_response_client,
        "Client",
        mqtt_request_response_client_binding);
}