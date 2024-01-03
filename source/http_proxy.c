/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "http.h"

#include "io.h"

#include <aws/http/connection.h>
#include <aws/http/proxy.h>

bool aws_py_http_proxy_options_init(struct aws_http_proxy_options *proxy_options, PyObject *py_proxy_options) {
    AWS_ZERO_STRUCT(*proxy_options);

    bool success = false;

    /* These references all need to be cleaned up before function returns */
    PyObject *py_host_name = NULL;
    PyObject *py_tls_options = NULL;
    PyObject *py_username = NULL;
    PyObject *py_password = NULL;

    py_host_name = PyObject_GetAttrString(py_proxy_options, "host_name");
    proxy_options->host = aws_byte_cursor_from_pyunicode(py_host_name);
    if (!proxy_options->host.ptr) {
        PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.host_name is not a valid string");
        goto done;
    }

    proxy_options->port = PyObject_GetAttrAsUint32(py_proxy_options, "HttpProxyOptions", "port");
    if (PyErr_Occurred()) {
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

    proxy_options->auth_type = PyObject_GetAttrAsIntEnum(py_proxy_options, "HttpProxyOptions", "auth_type");
    if (PyErr_Occurred()) {
        goto done;
    }

    py_username = PyObject_GetAttrString(py_proxy_options, "auth_username");
    if (py_username != Py_None) {
        proxy_options->auth_username = aws_byte_cursor_from_pyunicode(py_username);
        if (!proxy_options->auth_username.ptr) {
            PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.auth_username is not a valid string");
            goto done;
        }
    }

    py_password = PyObject_GetAttrString(py_proxy_options, "auth_password");
    if (py_password != Py_None) {
        proxy_options->auth_password = aws_byte_cursor_from_pyunicode(py_password);
        if (!proxy_options->auth_password.ptr) {
            PyErr_SetString(PyExc_TypeError, "HttpProxyOptions.auth_password is not a valid string");
            goto done;
        }
    }

    proxy_options->connection_type = PyObject_GetAttrAsIntEnum(py_proxy_options, "HttpProxyOptions", "connection_type");
    if (PyErr_Occurred()) {
        goto done;
    }

    success = true;
done:
    Py_XDECREF(py_host_name);
    Py_XDECREF(py_tls_options);
    Py_XDECREF(py_username);
    Py_XDECREF(py_password);
    if (!success) {
        AWS_ZERO_STRUCT(*proxy_options);
    }
    return success;
}
