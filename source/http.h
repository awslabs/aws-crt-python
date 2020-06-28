#ifndef AWS_CRT_PYTHON_HTTP_H
#define AWS_CRT_PYTHON_HTTP_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

struct aws_http_headers;
struct aws_http_message;
struct aws_http_proxy_options;

/**
 * Init aws_http_proxy_options from HttpProxyOptions.
 * Returns false and sets python exception if error occurred.
 *
 * NOTE: The native struct must be used immediately because it's cursors
 * reference memory from strings in the PyObject.
 * If we need this struct to be a long-lived object, we'll need to do a full binding.
 */
bool aws_py_http_proxy_options_init(struct aws_http_proxy_options *proxy_options, PyObject *py_proxy_options);

/**
 * Close the connection if it's open.
 */
PyObject *aws_py_http_connection_close(PyObject *self, PyObject *args);

/**
 * Returns True if connection is open and usable, False otherwise.
 */
PyObject *aws_py_http_connection_is_open(PyObject *self, PyObject *args);

/**
 * Create a new connection. returns void. The on_setup callback will be invoked
 * upon either success or failure of the connection.
 */
PyObject *aws_py_http_client_connection_new(PyObject *self, PyObject *args);

PyObject *aws_py_http_client_stream_new(PyObject *self, PyObject *args);

PyObject *aws_py_http_client_stream_activate(PyObject *self, PyObject *args);

/* Create capsule around new request-style aws_http_message struct */
PyObject *aws_py_http_message_new_request(PyObject *self, PyObject *args);

/* Create capsule to bind existing request-style aws_http_message struct. */
PyObject *aws_py_http_message_new_request_from_native(struct aws_http_message *request);

PyObject *aws_py_http_message_get_request_method(PyObject *self, PyObject *args);
PyObject *aws_py_http_message_set_request_method(PyObject *self, PyObject *args);
PyObject *aws_py_http_message_get_request_path(PyObject *self, PyObject *args);
PyObject *aws_py_http_message_set_request_path(PyObject *self, PyObject *args);
PyObject *aws_py_http_message_get_body_stream(PyObject *self, PyObject *args);
PyObject *aws_py_http_message_set_body_stream(PyObject *self, PyObject *args);

/* Create capsule to bind existing aws_http_headers struct. */
PyObject *aws_py_http_headers_new_from_native(struct aws_http_headers *headers);

/* Create capsule around new aws_http_headers struct */
PyObject *aws_py_http_headers_new(PyObject *self, PyObject *args);

PyObject *aws_py_http_headers_add(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_add_pairs(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_set(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_get(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_get_index(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_count(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_remove(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_remove_value(PyObject *self, PyObject *args);
PyObject *aws_py_http_headers_clear(PyObject *self, PyObject *args);

/* Given a python object, return a pointer to its underlying native type.
 * If NULL is returned, a python error has been set */

struct aws_http_connection *aws_py_get_http_connection(PyObject *connection);
struct aws_http_stream *aws_py_get_http_stream(PyObject *stream);
struct aws_http_message *aws_py_get_http_message(PyObject *http_message);
struct aws_http_headers *aws_py_get_http_headers(PyObject *http_headers);

#endif /* AWS_CRT_PYTHON_HTTP_H */
