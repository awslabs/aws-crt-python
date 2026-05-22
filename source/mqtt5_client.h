#ifndef AWS_CRT_PYTHON_MQTT5_CLIENT_H
#define AWS_CRT_PYTHON_MQTT5_CLIENT_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "module.h"

#include <aws/mqtt/mqtt.h>

/**
 * Parse a Python metrics object (with library_name and metadata_entries attrs)
 * into an aws_mqtt_iot_metrics struct. On success, returns true and populates
 * out_metrics. The caller must call aws_py_metrics_clean_up() when done.
 *
 * On failure, returns false and a Python error has been set.
 */
bool aws_py_metrics_parse(PyObject *metrics_py, struct aws_mqtt_iot_metrics *out_metrics);

/**
 * Clean up resources allocated by aws_py_metrics_parse().
 */
void aws_py_metrics_clean_up(struct aws_mqtt_iot_metrics *metrics);

PyObject *aws_py_mqtt5_client_new(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_start(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_stop(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_publish(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_subscribe(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_unsubscribe(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_get_stats(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_invoke_publish_acknowledgement(PyObject *self, PyObject *args);

PyObject *aws_py_mqtt5_ws_handshake_transform_complete(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */
struct aws_mqtt5_client *aws_py_get_mqtt5_client(PyObject *mqtt5_client);

#endif /* AWS_CRT_PYTHON_MQTT5_CLIENT_H */
