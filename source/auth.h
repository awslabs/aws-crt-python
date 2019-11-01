#ifndef AWS_CRT_PYTHON_AUTH_H
#define AWS_CRT_PYTHON_AUTH_H
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

PyObject *aws_py_credentials_provider_get_credentials(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_shutdown(PyObject *self, PyObject *args);

PyObject *aws_py_credentials_provider_new_chain_default(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_static(PyObject *self, PyObject *args);

PyObject *aws_py_signer_new_aws(PyObject *self, PyObject *args);
PyObject *aws_py_signer_sign_request(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */

struct aws_credentials_provider *aws_py_get_credentials_provider(PyObject *credentials_provider);
struct aws_signer *aws_py_get_signer(PyObject *signer);

#endif // AWS_CRT_PYTHON_AUTH_H
