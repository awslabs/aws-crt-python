#ifndef AWS_CRT_PYTHON_HTTP_CLIENT_CONNECTION_H
#define AWS_CRT_PYTHON_HTTP_CLIENT_CONNECTION_H
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
#include "http_connection.h"
#include <aws/http/connection.h>

/**
 * Create a new connection. returns void. The on_setup callback will be invoked
 * upon either success or failure of the connection.
 */
PyObject *aws_py_http_client_connection_create(PyObject *self, PyObject *args);
/**
 * Initiates a request on connection.
 */
PyObject *aws_py_http_client_connection_make_request(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_HTTP_CLIENT_CONNECTION_H */