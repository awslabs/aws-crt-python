#ifndef AWS_CRT_PYTHON_MQTT5_LISTENER_H
#define AWS_CRT_PYTHON_MQTT5_LISTENER_H
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

PyObject *aws_py_mqtt5_listener_new(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */
struct aws_mqtt5_listener *aws_py_get_mqtt5_listener(PyObject *mqtt5_listener);

#endif /* AWS_CRT_PYTHON_MQTT5_LISTENER_H */
