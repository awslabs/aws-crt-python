#ifndef AWS_CRT_PYTHON_EVENT_STREAM_H
#define AWS_CRT_PYTHON_EVENT_STREAM_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

struct aws_array_list;
struct aws_event_stream_header_value_pair;

PyObject *aws_py_event_stream_rpc_client_connection_connect(PyObject *self, PyObject *args);
PyObject *aws_py_event_stream_rpc_client_connection_close(PyObject *self, PyObject *args);
PyObject *aws_py_event_stream_rpc_client_connection_is_open(PyObject *self, PyObject *args);
PyObject *aws_py_event_stream_rpc_client_connection_send_protocol_message(PyObject *self, PyObject *args);

/**
 * Given a python list of EventStreamHeaders, init an aws_array_list of aws_event_stream_header_value_pairs.
 * All variable-length values are copied (owned) by the new headers.
 * Returns false and sets python exception if error occurred.
 */
bool aws_py_event_stream_native_headers_init(struct aws_array_list *native_headers, PyObject *headers_py);

/**
 * Given an array of aws_event_stream_header_value_pair, create a python list containing (name, value, type) tuples.
 * Returns a new reference if successful.
 * Returns NULL and sets a python exception if error occurs.
 */
PyObject *aws_py_event_stream_python_headers_create(
    struct aws_event_stream_header_value_pair *native_headers,
    size_t count);

#endif /* AWS_CRT_PYTHON_EVENT_STREAM_H */
