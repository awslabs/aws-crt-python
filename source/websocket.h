#ifndef AWS_CRT_PYTHON_WEBSOCKET_H
#define AWS_CRT_PYTHON_WEBSOCKET_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

PyObject *aws_py_websocket_client_connect(PyObject *self, PyObject *args);
PyObject *aws_py_websocket_close(PyObject *self, PyObject *args);
PyObject *aws_py_websocket_send_frame(PyObject *self, PyObject *args);
PyObject *aws_py_websocket_increment_read_window(PyObject *self, PyObject *args);
PyObject *aws_py_websocket_create_handshake_request(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_WEBSOCKET_H */
