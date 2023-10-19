#ifndef AWS_CRT_PYTHON_IO_H
#define AWS_CRT_PYTHON_IO_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

/**
 * This file includes definitions for common aws-c-io functions.
 */

#include "module.h"

struct aws_socket_options;

/**
 *  Init aws_socket_options from SocketOptions. Returns false and sets python exception if error occurred.
 */
bool aws_py_socket_options_init(struct aws_socket_options *socket_options, PyObject *py_socket_options);

/**
 * Returns a capsule for logging and starts the logging sub-system
 */
PyObject *aws_py_init_logging(PyObject *self, PyObject *args);

/**
 * Returns True if ALPN is available, False if it is not.
 */
PyObject *aws_py_is_alpn_available(PyObject *self, PyObject *args);

/**
 * Returns True if the input TLS Cipher Preference Enum is supported on the current platform. False otherwise.
 */
PyObject *aws_py_is_tls_cipher_supported(PyObject *self, PyObject *args);

/**
 * Create a new event_loop_group to be managed by a Python Capsule.
 */
PyObject *aws_py_event_loop_group_new(PyObject *self, PyObject *args);

/**
 * Create a new default host_resolver to be managed by a Python Capsule.
 */
PyObject *aws_py_host_resolver_new_default(PyObject *self, PyObject *args);

/**
 * Create a new client_bootstrap to be managed by a Python Capsule.
 */
PyObject *aws_py_client_bootstrap_new(PyObject *self, PyObject *args);

/**
 * Create a new tls_ctx to be managed by a Python Capsule.
 */
PyObject *aws_py_client_tls_ctx_new(PyObject *self, PyObject *args);

PyObject *aws_py_tls_connections_options_new_from_ctx(PyObject *self, PyObject *args);

PyObject *aws_py_tls_connection_options_set_alpn_list(PyObject *self, PyObject *args);

PyObject *aws_py_tls_connection_options_set_server_name(PyObject *self, PyObject *args);

/**
 * Create a new aws_input_stream to be managed by a Python capsule.
 */
PyObject *aws_py_input_stream_new(PyObject *self, PyObject *args);

/**
 * Create a new aws_pkcs11_lib to be managed by a Python capsule.
 */
PyObject *aws_py_pkcs11_lib_new(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */

struct aws_event_loop_group *aws_py_get_event_loop_group(PyObject *event_loop_group);
struct aws_host_resolver *aws_py_get_host_resolver(PyObject *host_resolver);
struct aws_client_bootstrap *aws_py_get_client_bootstrap(PyObject *client_bootstrap);
struct aws_tls_ctx *aws_py_get_tls_ctx(PyObject *tls_ctx);
struct aws_tls_connection_options *aws_py_get_tls_connection_options(PyObject *tls_connection_options);
struct aws_input_stream *aws_py_get_input_stream(PyObject *input_stream);
struct aws_pkcs11_lib *aws_py_get_pkcs11_lib(PyObject *pkcs11_lib);

#endif /* AWS_CRT_PYTHON_IO_H */
