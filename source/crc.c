/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "checksums.h"

#include "aws/checksums/crc.h"
#include "aws/common/byte_buf.h"

PyObject *aws_py_checksums_crc32(PyObject *self, PyObject *args) {
    (void)self;

    Py_buffer input;
    PyObject *py_previousCrc32;

    if (!PyArg_ParseTuple(args, "s*O", &input, &py_previousCrc32)) {
        return NULL;
    }

    /* Note: PyArg_ParseTuple() doesn't do overflow checking on unsigned values
     * so use PyLong_AsUnsignedLong() to get the value of the previousCrc arg */
    uint32_t previousCrc32 = PyLong_AsUnsignedLong(py_previousCrc32);

    if (previousCrc32 == (uint32_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    if (!PyBuffer_IsContiguous(&input, 'C')) {
        PyErr_SetString(PyExc_ValueError, "input must be contiguous buffer");
        return NULL;
    }

    uint32_t crc_res = aws_checksums_crc32(input.buf, input.len, previousCrc32);

    return PyLong_FromUnsignedLong(crc_res);
}

PyObject *aws_py_checksums_crc32c(PyObject *self, PyObject *args) {
    (void)self;

    Py_buffer input;
    PyObject *py_previousCrc32c;

    if (!PyArg_ParseTuple(args, "s*O", &input, &py_previousCrc32c)) {
        return NULL;
    }

    /* Note: PyArg_ParseTuple() doesn't do overflow checking on unsigned values
     * so use PyLong_AsUnsignedLong() to get the value of the previousCrc arg */
    uint32_t previousCrc32c = PyLong_AsUnsignedLong(py_previousCrc32c);

    if (previousCrc32c == (uint32_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    if (!PyBuffer_IsContiguous(&input, 'C')) {
        PyErr_SetString(PyExc_ValueError, "input must be contiguous buffer");
        return NULL;
    }

    uint32_t crc_res = aws_checksums_crc32c(input.buf, input.len, previousCrc32c);

    return PyLong_FromUnsignedLong(crc_res);
}
