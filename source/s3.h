#ifndef AWS_CRT_PYTHON_S3_H
#define AWS_CRT_PYTHON_S3_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "module.h"
struct aws_s3_tcp_keep_alive_options;

bool aws_s3_tcp_keep_alive_options_init(struct aws_s3_tcp_keep_alive_options *tcp_keep_alive_options, PyObject *py_tcp_keep_alive_options);

PyObject *aws_py_s3_client_new(PyObject *self, PyObject *args);
PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args);

PyObject *aws_py_s3_meta_request_cancel(PyObject *self, PyObject *args);

struct aws_s3_client *aws_py_get_s3_client(PyObject *s3_client);
struct aws_s3_meta_request *aws_py_get_s3_meta_request(PyObject *s3_client);

#endif /* AWS_CRT_PYTHON_S3_H */
