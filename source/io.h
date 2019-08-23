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
 * Name String to logging capsules
 */
extern const char *s_capsule_name_logger;

/**
 * Returns a capsule for logging and starts the logging sub-system
 */
PyObject *aws_py_io_init_logging(PyObject *self, PyObject *args);

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

PyObject *aws_py_io_tls_connections_options_new_from_ctx(PyObject *self, PyObject *args);

PyObject *aws_py_io_tls_connection_options_set_alpn_list(PyObject *self, PyObject *args);

PyObject *aws_py_io_tls_connection_options_set_server_name(PyObject *self, PyObject *args);


/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */

struct aws_event_loop_group *get_aws_event_loop_group(PyObject *event_loop_group);
struct aws_host_resolver *get_aws_host_resolver(PyObject *host_resolver);
struct aws_client_bootstrap *get_aws_client_bootstrap(PyObject *client_bootstrap);
struct aws_tls_ctx *get_aws_tls_ctx(PyObject *tls_ctx);
struct aws_tls_connection_options *get_aws_tls_connection_options(PyObject *tls_connection_options);

#endif /* AWS_CRT_PYTHON_IO_H */
