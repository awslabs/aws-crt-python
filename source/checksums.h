#ifndef AWS_CRT_PYTHON_CHECKSUMS_H
#define AWS_CRT_PYTHON_CHECKSUMS_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

PyObject *aws_py_checksums_crc32(PyObject *self, PyObject *args);
PyObject *aws_py_checksums_crc32c(PyObject *self, PyObject *args);
PyObject *aws_py_checksums_crc64nvme(PyObject *self, PyObject *args);
PyObject *aws_py_checksums_crc32_combine(PyObject *self, PyObject *args);
PyObject *aws_py_checksums_crc32c_combine(PyObject *self, PyObject *args);
PyObject *aws_py_checksums_crc64nvme_combine(PyObject *self, PyObject *args);

PyObject *aws_py_xxhash64_new(PyObject *self, PyObject *args);
PyObject *aws_py_xxhash3_64_new(PyObject *self, PyObject *args);
PyObject *aws_py_xxhash3_128_new(PyObject *self, PyObject *args);
PyObject *aws_py_xxhash64_compute(PyObject *self, PyObject *args);
PyObject *aws_py_xxhash3_64_compute(PyObject *self, PyObject *args);
PyObject *aws_py_xxhash3_128_compute(PyObject *self, PyObject *args);
PyObject *aws_py_xxhash_update(PyObject *self, PyObject *args);
PyObject *aws_py_xxhash_finalize(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_CHECKSUMS_H */
