#ifndef AWS_CRT_PYTHON_COMMON_H
#define AWS_CRT_PYTHON_COMMON_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

/**
 * This file includes definitions for common aws-c-common functions.
 */

#include "module.h"

PyObject *aws_py_get_cpu_group_count(PyObject *self, PyObject *args);
PyObject *aws_py_get_cpu_count_for_group(PyObject *self, PyObject *args);

PyObject *aws_py_thread_join_all_managed(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_COMMON_H */
