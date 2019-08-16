#ifndef AWS_CRT_PYTHON_HTTP_CONNECTION_H
#define AWS_CRT_PYTHON_HTTP_CONNECTION_H
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

extern const char *s_capsule_name_http_connection;

struct py_http_connection{
    struct aws_allocator *allocator;
    struct aws_http_connection *connection;
    PyObject *capsule;
    PyObject *on_connection_shutdown;
    bool destructor_called;
    bool shutdown_called;

    /* client side */
    PyObject *on_connection_setup;
    PyObject *bootstrap;

    /*server side */
    PyObject *on_incoming_request;
    PyObject *server_capsule;
};

void s_http_connection_destructor(PyObject *http_server_conn_capsule);

/**
 * Close the connection if it's open.
 */
PyObject *aws_py_http_connection_close(PyObject *self, PyObject *args);
/**
 * Returns True if connection is open and usable, False otherwise.
 */
PyObject *aws_py_http_connection_is_open(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_HTTP_CONNECTION_H */
