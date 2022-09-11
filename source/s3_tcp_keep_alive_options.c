/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "s3.h"

#include <aws/s3/s3_client.h>

bool aws_s3_tcp_keep_alive_options_init(struct aws_s3_tcp_keep_alive_options *tcp_keep_alive_options, PyObject *py_tcp_keep_alive_options) {
    AWS_ZERO_STRUCT(*tcp_keep_alive_options);
    bool success = false;

    tcp_keep_alive_options->keep_alive_interval_sec = PyObject_GetAttrAsUint16(py_tcp_keep_alive_options, "S3TcpKeepAliveOptions", "keep_alive_interval_sec");
    if (PyErr_Occurred()) {
        goto done;
    }

    tcp_keep_alive_options->keep_alive_timeout_sec = PyObject_GetAttrAsUint16(py_tcp_keep_alive_options, "S3TcpKeepAliveOptions", "keep_alive_timeout_sec");
    if (PyErr_Occurred()) {
        goto done;
    }

    tcp_keep_alive_options->keep_alive_max_failed_probes = PyObject_GetAttrAsUint16(py_tcp_keep_alive_options, "S3TcpKeepAliveOptions", "keep_alive_max_failed_probes");
    if (PyErr_Occurred()) {
        goto done;
    }

    success = true;

done:
    return success;
}