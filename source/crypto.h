#ifndef AWS_CRT_PYTHON_CRYPTO_H
#define AWS_CRT_PYTHON_CRYPTO_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

/** Name string for hash capsule. */
extern const char *s_capsule_name_hash;
/** Name string for hmac capsule. */
extern const char *s_capsule_name_hmac;

PyObject *aws_py_sha1_new(PyObject *self, PyObject *args);
PyObject *aws_py_sha256_new(PyObject *self, PyObject *args);
PyObject *aws_py_md5_new(PyObject *self, PyObject *args);

PyObject *aws_py_hash_update(PyObject *self, PyObject *args);
PyObject *aws_py_hash_digest(PyObject *self, PyObject *args);

PyObject *aws_py_sha256_hmac_new(PyObject *self, PyObject *args);

PyObject *aws_py_hmac_update(PyObject *self, PyObject *args);
PyObject *aws_py_hmac_digest(PyObject *self, PyObject *args);

PyObject *aws_py_sha256_compute(PyObject *self, PyObject *args);
PyObject *aws_py_md5_compute(PyObject *self, PyObject *args);
PyObject *aws_py_sha256_hmac_compute(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_CRYPTO_H */
