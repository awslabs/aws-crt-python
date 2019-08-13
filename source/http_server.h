#ifndef AWS_CRT_PYTHON_HTTP_SERVER_H
#define AWS_CRT_PYTHON_HTTP_SERVER_H
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
#include <aws/http/connection.h>

extern const char *s_capsule_name_http_server;

/**
 * Create a new server. returns a server object.
 */
PyObject *aws_py_http_server_create(PyObject *self, PyObject *args);


/**
 * Release the server. It will close the listening socket and all the connections existing in the server.
 * The on_destroy_complete will be invoked when the destroy operation completes
 */
PyObject *aws_py_http_server_realease(PyObject *self, PyObject *args);

/**
 * Configure a server connection. When a new connection is received, the on_incoming callback will be fired, 
 * and user must call new_server_connection() to configure the connection, and this function will be called from
 * new_server_connection()
 */
PyObject *aws_py_http_connection_configure_server(PyObject *self, PyObject *args);

/**
 * Close the server connection.
 */
PyObject *aws_py_http_server_connection_close(PyObject *self, PyObject *args);

/**
 * Create a stream, with a server connection receiving and responding to a request.
 * This function can only be called from the `aws_http_on_incoming_request_fn` callback.
 * aws_py_http_stream_send_response() should be used to send a response.
 */
PyObject *aws_py_http_stream_new_server_request_handler(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_HTTP_CLIENT_CONNECTION_H */
