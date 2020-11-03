#ifndef AWS_CRT_PYTHON_S3_CLIENT_H
#define AWS_CRT_PYTHON_S3_CLIENT_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "module.h"

#include <aws/s3/s3_client.h>

PyObject *aws_py_s3_client_new(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */
struct aws_mqtt_client *aws_py_get_mqtt_client(PyObject *mqtt_client);

#endif /* AWS_CRT_PYTHON_S3_CLIENT_H */
