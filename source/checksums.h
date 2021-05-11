#ifndef AWS_CRT_PYTHON_CHECKSUMS_H
#define AWS_CRT_PYTHON_CHECKSUMS_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

PyObject *aws_py_checksums_crc32(PyObject *self, PyObject *args);
PyObject *aws_py_checksums_crc32c(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_CHECKSUMS_H */
