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
#include "http_connection.h"

#include "io.h"

#include <aws/common/array_list.h>
#include <aws/http/request_response.h>
#include <aws/io/socket.h>
#include <aws/io/stream.h>

const char *s_capsule_name_http_connection = "aws_http_connection";

void s_http_connection_destructor(PyObject *http_connection_capsule) {
    struct py_http_connection *http_connection =
        PyCapsule_GetPointer(http_connection_capsule, s_capsule_name_http_connection);
    assert(http_connection);
    if (http_connection->on_incoming_request) {
        Py_DECREF(http_connection->on_incoming_request);
    }

    http_connection->destructor_called = true;

    if (http_connection->connection) {
        if (aws_http_connection_is_open(http_connection->connection)) {
            aws_http_connection_close(http_connection->connection);
        }
        if (http_connection->shutdown_called) {
            aws_http_connection_release(http_connection->connection);
            /* server side */
            if (http_connection->server_capsule) {
                Py_DECREF(http_connection->server_capsule);
            }
            /* client side */
            if (http_connection->bootstrap) {
                Py_DECREF(http_connection->bootstrap);
                http_connection->bootstrap = NULL;
            }

            http_connection->connection = NULL;
        }
    } else if (http_connection->shutdown_called) {
        /* server side */
        if (http_connection->server_capsule) {
            Py_DECREF(http_connection->server_capsule);
        }
        /* client side */
        if (http_connection->bootstrap) {
            Py_DECREF(http_connection->bootstrap);
            http_connection->bootstrap = NULL;
        }
        aws_mem_release(http_connection->allocator, http_connection);
    }
}

PyObject *aws_py_http_connection_is_open(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *http_impl = NULL;

    if (PyArg_ParseTuple(args, "O", &http_impl)) {
        if (http_impl) {
            struct py_http_connection *http_connection =
                PyCapsule_GetPointer(http_impl, s_capsule_name_http_connection);
            assert(http_connection);

            if (http_connection->connection && aws_http_connection_is_open(http_connection->connection)) {
                Py_RETURN_TRUE;
            }
        }
    }

    Py_RETURN_FALSE;
}

PyObject *aws_py_http_connection_close(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *http_impl = NULL;

    if (PyArg_ParseTuple(args, "O", &http_impl)) {
        if (http_impl) {
            struct py_http_connection *http_connection =
                PyCapsule_GetPointer(http_impl, s_capsule_name_http_connection);
            assert(http_connection);

            if (http_connection->connection) {
                aws_http_connection_close(http_connection->connection);
            }
        }
    }

    Py_RETURN_NONE;
}
