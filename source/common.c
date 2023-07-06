/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "common.h"

#include <aws/common/system_info.h>
#include <aws/common/thread.h>

PyObject *aws_py_get_cpu_group_count(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    uint16_t count = aws_get_cpu_group_count();
    return PyLong_FromUnsignedLong(count);
}

PyObject *aws_py_get_cpu_count_for_group(PyObject *self, PyObject *args) {
    (void)self;

    uint16_t group_idx;
    if (!PyArg_ParseTuple(args, "H", &group_idx)) {
        return NULL;
    }

    size_t count = aws_get_cpu_count_for_group(group_idx);
    return PyLong_FromSize_t(count);
}

PyObject *aws_py_thread_join_all_managed(PyObject *self, PyObject *args) {
    (void)self;

    double timeout_sec = 0.0;
    if (!PyArg_ParseTuple(args, "d", &timeout_sec)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }

    /* Actual call uses 0 to denote "wait forever" */
    uint64_t timeout_ns;
    if (timeout_sec < 0.0) {
        timeout_ns = 0;
    } else {
        timeout_ns = (uint64_t)(timeout_sec * 1000000000);
        if (timeout_ns == 0) {
            timeout_ns = 1;
        }
    }
    aws_thread_set_managed_join_timeout_ns(timeout_ns);

    if (aws_thread_join_all_managed()) {
        Py_RETURN_FALSE;
    }

    Py_RETURN_TRUE;
}
