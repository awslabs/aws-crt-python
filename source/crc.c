/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "checksums.h"

#include "aws/checksums/crc.h"
#include "aws/common/byte_buf.h"

PyObject *aws_py_checksums_crc32(PyObject *self, PyObject *args) {
    (void)self;
    // (void)args;

    Py_buffer input_buf;
    PyObject *py_previousCrc32;

    if (!PyArg_ParseTuple(args, "s*O", &input_buf, &py_previousCrc32)) {
        return PyErr_AwsLastError();
    }

    uint32_t previousCrc32 = PyLong_AsUnsignedLong(py_previousCrc32);

    if (previousCrc32 == (uint32_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    struct aws_byte_buf input = aws_byte_buf_from_array(input_buf.buf, input_buf.len);

    uint32_t crc_res = aws_checksums_crc32(input.buffer, input.len, previousCrc32);

    return PyLong_FromUnsignedLong(crc_res);
}

PyObject *aws_py_checksums_crc32c(PyObject *self, PyObject *args) {
    (void)self;
    // (void)args;

    Py_buffer input_buf;
    PyObject *py_previousCrc32c;

    if (!PyArg_ParseTuple(args, "s*O", &input_buf, &py_previousCrc32c)) {
        return PyErr_AwsLastError();
    }

    uint32_t previousCrc32c = PyLong_AsUnsignedLong(py_previousCrc32c);

    if (previousCrc32c == (uint32_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    struct aws_byte_buf input = aws_byte_buf_from_array(input_buf.buf, input_buf.len);

    uint32_t crc_res = aws_checksums_crc32c(input.buffer, input.len, previousCrc32c);

    return PyLong_FromUnsignedLong(crc_res);
}
