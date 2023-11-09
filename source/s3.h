#ifndef AWS_CRT_PYTHON_S3_H
#define AWS_CRT_PYTHON_S3_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "module.h"

PyObject *aws_py_s3_get_ec2_instance_type(PyObject *self, PyObject *args);
PyObject *aws_py_s3_is_crt_s3_optimized_for_system(PyObject *self, PyObject *args);
PyObject *aws_py_s3_get_recommended_throughput_target_gbps(PyObject *self, PyObject *args);
PyObject *aws_py_s3_get_optimized_platforms(PyObject *self, PyObject *args);

PyObject *aws_py_s3_client_new(PyObject *self, PyObject *args);
PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args);

PyObject *aws_py_s3_meta_request_cancel(PyObject *self, PyObject *args);

PyObject *aws_py_s3_cross_process_lock_new(PyObject *self, PyObject *args);
PyObject *aws_py_s3_cross_process_lock_acquire(PyObject *self, PyObject *args);
PyObject *aws_py_s3_cross_process_lock_release(PyObject *self, PyObject *args);

struct aws_s3_client *aws_py_get_s3_client(PyObject *s3_client);
struct aws_s3_meta_request *aws_py_get_s3_meta_request(PyObject *s3_client);

#endif /* AWS_CRT_PYTHON_S3_H */
