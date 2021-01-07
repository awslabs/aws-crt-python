/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "common.h"

#include <aws/common/system_info.h>

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

PyObject *aws_py_get_cpu_ids_for_group(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *alloc = aws_py_get_allocator();

    uint16_t group_idx;
    if (!PyArg_ParseTuple(args, "H", &group_idx)) {
        return NULL;
    }

    size_t count = aws_get_cpu_count_for_group(group_idx);

    /* From hereon, we need to clean up if errors occur */
    PyObject *py_list = NULL;
    struct aws_cpu_info *cpu_array = NULL;

    /* Get CPU info from C */
    cpu_array = aws_mem_acquire(alloc, count * sizeof(struct aws_cpu_info));
    if (!cpu_array) {
        PyErr_AwsLastError();
        goto error;
    }

    aws_get_cpu_ids_for_group(group_idx, cpu_array, count);

    /* Copy CPU info into python list */
    py_list = PyList_New(count);
    if (!py_list) {
        goto error;
    }

    for (size_t i = 0; i < count; ++i) {
        PyObject *py_id = PyLong_FromLong(cpu_array[i].cpu_id);
        if (!py_id) {
            goto error;
        }
        PyList_SET_ITEM(py_list, i, py_id); /* Steals reference */
    }

    /* Success */
    aws_mem_release(alloc, cpu_array);
    return py_list;

error:
    aws_mem_release(alloc, cpu_array);
    Py_XDECREF(py_list);
    return NULL;
}
