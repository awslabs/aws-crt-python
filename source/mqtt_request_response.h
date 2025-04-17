#ifndef AWS_CRT_PYTHON_MQTT_REQUEST_RESPONSE_H
#define AWS_CRT_PYTHON_MQTT_REQUEST_RESPONSE_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "module.h"

struct aws_mqtt_request_response_client;

PyObject *aws_py_mqtt_request_response_client_new_from_5(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt_request_response_client_new_from_311(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt_request_response_client_make_request(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt_request_response_client_create_stream(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt_streaming_operation_open(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */
struct aws_mqtt_request_response_client *aws_py_get_mqtt_request_response_client(
    PyObject *mqtt_request_response_client);

struct aws_mqtt_rr_client_operation *aws_py_get_mqtt_streaming_operation(PyObject *mqtt_streaming_operation);

#endif /* AWS_CRT_PYTHON_MQTT_REQUEST_RESPONSE_H */