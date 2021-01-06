#ifndef AWS_CRT_PYTHON_AUTH_H
#define AWS_CRT_PYTHON_AUTH_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

struct aws_credentials;

PyObject *aws_py_credentials_new(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_access_key_id(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_secret_access_key(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_session_token(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_expiration_timestamp_seconds(PyObject *self, PyObject *args);

PyObject *aws_py_credentials_provider_get_credentials(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_chain_default(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_static(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_profile(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_process(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_environment(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_chain(PyObject *self, PyObject *args);
PyObject *aws_py_credentials_provider_new_delegate(PyObject *self, PyObject *args);

PyObject *aws_py_signing_config_new(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_algorithm(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_signature_type(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_credentials_provider(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_region(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_service(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_date(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_use_double_uri_encode(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_should_normalize_uri_path(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_signed_body_value(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_signed_body_header_type(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_expiration_in_seconds(PyObject *self, PyObject *args);
PyObject *aws_py_signing_config_get_omit_session_token(PyObject *self, PyObject *args);

PyObject *aws_py_sign_request_aws(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */

struct aws_credentials *aws_py_get_credentials(PyObject *credentials);
struct aws_credentials_provider *aws_py_get_credentials_provider(PyObject *credentials_provider);
struct aws_signing_config_aws *aws_py_get_signing_config(PyObject *signing_config);

#endif // AWS_CRT_PYTHON_AUTH_H
