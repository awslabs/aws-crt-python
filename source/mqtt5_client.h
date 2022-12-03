#ifndef AWS_CRT_PYTHON_MQTT5_CLIENT_H
#define AWS_CRT_PYTHON_MQTT5_CLIENT_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

/**
 * DEVELOPER PREVIEW DISCLAIMER
 *
 * MQTT5 support is currently in **developer preview**.  We encourage feedback at all times, but feedback during the
 * preview window is especially valuable in shaping the final product.  During the preview period we may make
 * backwards-incompatible changes to the public API, but in general, this is something we will try our best to avoid.
 */

#include "module.h"

PyObject *aws_py_mqtt5_client_new(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_start(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_stop(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_publish(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_subscribe(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_unsubscribe(PyObject *self, PyObject *args);
PyObject *aws_py_mqtt5_client_get_stats(PyObject *self, PyObject *args);

PyObject *aws_py_mqtt5_ws_handshake_transform_complete(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */
struct aws_mqtt5_client *aws_py_get_mqtt5_client(PyObject *mqtt5_client);

#endif /* AWS_CRT_PYTHON_MQTT5_CLIENT_H */
