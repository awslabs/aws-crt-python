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
        if (input.obj) {
            PyBuffer_Release(&input);
        }
        PyErr_SetString(PyExc_ValueError, "input must be contiguous buffer");
        return NULL;
    }

    uint32_t signed_val = previousCrc32;

    /* Releasing the GIL for very small buffers is inefficient
       and may lower performance */
    if (input.len > 1024 * 5) {
        unsigned char *buf = input.buf;
        Py_ssize_t len = input.len;

        /* clang-format off */
        Py_BEGIN_ALLOW_THREADS
            /* Avoid truncation of length for very large buffers. crc32() takes
               length as an unsigned int, which may be narrower than Py_ssize_t. */
            while ((size_t)len > UINT_MAX) {
                signed_val = aws_checksums_crc32(buf, UINT_MAX, signed_val);
                buf += (size_t)UINT_MAX;
                len -= (size_t)UINT_MAX;
            }
            signed_val = aws_checksums_crc32(buf, (unsigned int)len, signed_val);
        Py_END_ALLOW_THREADS
        /* clang-format on */
    } else {
        signed_val = aws_checksums_crc32(input.buf, (unsigned int)input.len, signed_val);
    }
    if (input.obj) {
        PyBuffer_Release(&input);
    }
    /* why the bitwise and? */
    return PyLong_FromUnsignedLong(signed_val);
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
        if (input.obj) {
            PyBuffer_Release(&input);
        }
        return NULL;
    }

    if (!PyBuffer_IsContiguous(&input, 'C')) {
        PyErr_SetString(PyExc_ValueError, "input must be contiguous buffer");
        return NULL;
    }

    int signed_val = previousCrc32c;

    /* Releasing the GIL for very small buffers is inefficient
       and may lower performance */
    if (input.len > 1024 * 5) {
        unsigned char *buf = input.buf;
        Py_ssize_t len = input.len;

        Py_BEGIN_ALLOW_THREADS
            /* Avoid truncation of length for very large buffers. crc32() takes
               length as an unsigned int, which may be narrower than Py_ssize_t. */
            while ((size_t)len > UINT_MAX) {
            signed_val = aws_checksums_crc32c(buf, UINT_MAX, signed_val);
            buf += (size_t)UINT_MAX;
            len -= (size_t)UINT_MAX;
        }
        signed_val = aws_checksums_crc32c(buf, (unsigned int)len, signed_val);
        Py_END_ALLOW_THREADS
    } else {
        signed_val = aws_checksums_crc32c(input.buf, (unsigned int)input.len, signed_val);
    }
    if (input.obj) {
        PyBuffer_Release(&input);
    }
    /* why the bitwise and? */
    return PyLong_FromUnsignedLong(signed_val & 0xffffffffU);
}
