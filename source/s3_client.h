#ifndef AWS_CRT_PYTHON_S3_CLIENT_H
#define AWS_CRT_PYTHON_S3_CLIENT_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "module.h"

#include <aws/s3/s3_client.h>

PyObject *aws_py_s3_client_new(PyObject *self, PyObject *args);
PyObject *aws_py_s3_client_shutdown(PyObject *self, PyObject *args);
// PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args);

struct aws_s3_client *aws_py_get_s3_client(PyObject *s3_client);

#endif /* AWS_CRT_PYTHON_S3_CLIENT_H */
