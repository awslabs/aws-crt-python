#ifndef AWS_CRT_PYTHON_CRYPTO_H
#define AWS_CRT_PYTHON_CRYPTO_H
/*
 * Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *  http://aws.amazon.com/apache2.0
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */
#include "module.h"

/** Name string for hash capsule. */
extern const char *s_capsule_name_hash;
/** Name string for hmac capsule. */
extern const char *s_capsule_name_hmac;

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
