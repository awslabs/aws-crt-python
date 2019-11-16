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
#include "http.h"

#include "io.h"

#include <aws/http/connection.h>

bool aws_py_http_proxy_options_init(struct aws_http_proxy_options *proxy_options, PyObject *py_proxy_options) {
    AWS_ZERO_STRUCT(*proxy_options);

    bool success = false;

    /* These references all need to be cleaned up before function returns */
    PyObject *py_host_name = NULL;
    PyObject *py_port = NULL;
    PyObject *py_tls_options = NULL;
    PyObject *py_auth_type = NULL;
    PyObject *py_username = NULL;
    PyObject *py_password = NULL;

    py_host_name = PyObject_GetAttrString(py_proxy_options, "host_name");
    proxy_options->host = aws_byte_cursor_from_pystring(py_host_name);
    if (!proxy_options->host.ptr) {
        PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.host_name is not a valid string");
        goto done;
    }

    py_port = PyObject_GetAttrString(py_proxy_options, "port");
    long port_val = PyLong_AsLong(py_port); /* returns -1 on error */
    if (port_val < 0 || port_val > UINT16_MAX) {
        PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.port is not a valid number");
        goto done;
    }

    py_tls_options = PyObject_GetAttrString(py_proxy_options, "tls_connection_options");
    if (py_tls_options != Py_None) {
        proxy_options->tls_options = aws_py_get_tls_connection_options(py_tls_options);
        if (!proxy_options->tls_options) {
            PyErr_SetString(
                PyExc_TypeError, "HttpProxyOptions.tls_connection_options is not a valid TlsConnectionOptions");
            goto done;
        }
    }

    py_auth_type = PyObject_GetAttrString(py_proxy_options, "auth_type");
    long auth_type_val = PyIntEnum_AsLong(py_auth_type);
    switch (auth_type_val) {
        case AWS_HPAT_NONE:
            proxy_options->auth_type = AWS_HPAT_NONE;
            break;
        case AWS_HPAT_BASIC:
            proxy_options->auth_type = AWS_HPAT_BASIC;
            break;
        default:
            PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.auth_type is not a valid HttpProxyAuthenticationType");
            goto done;
    }

    py_username = PyObject_GetAttrString(py_proxy_options, "auth_username");
    if (py_username != Py_None) {
        proxy_options->auth_username = aws_byte_cursor_from_pystring(py_username);
        if (!proxy_options->auth_username.ptr) {
            PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.auth_username is not a valid string");
            goto done;
        }
    }

    py_password = PyObject_GetAttrString(py_proxy_options, "auth_password");
    if (py_password != Py_None) {
        proxy_options->auth_password = aws_byte_cursor_from_pystring(py_password);
        if (!proxy_options->auth_password.ptr) {
            PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.auth_password is not a valid string");
            goto done;
        }
    }

    success = true;
done:
    Py_XDECREF(py_host_name);
    Py_XDECREF(py_port);
    Py_XDECREF(py_tls_options);
    Py_XDECREF(py_auth_type);
    Py_XDECREF(py_username);
    Py_XDECREF(py_password);
    if (!success) {
        AWS_ZERO_STRUCT(*proxy_options);
    }
    return success;
}
