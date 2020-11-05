#ifndef AWS_CRT_PYTHON_EVENT_STREAM_H
#define AWS_CRT_PYTHON_EVENT_STREAM_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

PyObject *aws_py_event_stream_rpc_client_connection_connect(PyObject *self, PyObject *args);
PyObject *aws_py_event_stream_rpc_client_connection_close(PyObject *self, PyObject *args);
PyObject *aws_py_event_stream_rpc_client_connection_is_open(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_EVENT_STREAM_H */
