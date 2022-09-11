/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "http.h"

#include <aws/http/connection.h>

bool aws_http_connection_monitoring_options_init(struct aws_http_connection_monitoring_options *monitoring_options, PyObject *py_monitoring_options) {
    AWS_ZERO_STRUCT(*monitoring_options);
    bool success = false;

    monitoring_options->minimum_throughput_bytes_per_second = PyObject_GetAttrAsUint64(py_monitoring_options, "HttpMonitoringOptions", "min_throughput_bytes_per_second");
    if (PyErr_Occurred()) {
        goto done;
    }

    monitoring_options->allowable_throughput_failure_interval_seconds = PyObject_GetAttrAsUint32(py_monitoring_options, "HttpMonitoringOptions", "allowable_throughput_failure_interval_seconds");
    if (PyErr_Occurred()) {
        goto done;
    }
    success = true;

done:
    return success;
}