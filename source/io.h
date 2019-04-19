#ifndef AWS_CRT_PYTHON_IO_H
#define AWS_CRT_PYTHON_IO_H
/*
 * Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

/**
 * This file includes definitions for common aws-c-io functions.
 */

#include "module.h"

/**
 * Name string for event_loop_group capsules.
 */
extern const char *s_capsule_name_client_bootstrap;

/**
 * Name string for tls_ctx capsules.
 */
extern const char *s_capsule_name_tls_ctx;

/**
 * Returns True if ALPN is available, False if it is not.
 */
PyObject *aws_py_is_alpn_available(PyObject *self, PyObject *args);

/**
 * Create a new event_loop_group to be managed by a Python Capsule.
 */
PyObject *aws_py_io_event_loop_group_new(PyObject *self, PyObject *args);

/**
 * Create a new default host_resolver to be managed by a Python Capsule.
 */
PyObject *aws_py_io_host_resolver_new_default(PyObject *self, PyObject *args);

/**
 * Create a new client_bootstrap to be managed by a Python Capsule.
 */
PyObject *aws_py_io_client_bootstrap_new(PyObject *self, PyObject *args);

/**
 * Create a new tls_ctx to be managed by a Python Capsule.
 */
PyObject *aws_py_io_client_tls_ctx_new(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_IO_H */
