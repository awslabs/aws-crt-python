/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "checksums.h"

#include "aws/checksums/crc.h"
#include "aws/common/byte_buf.h"
PyObject *checksums_crc_common(PyObject *args, uint32_t (*checksum_fn)(const uint8_t *, int, uint32_t)) {
    Py_buffer input;
    PyObject *py_previousCrc;
    PyObject *py_result = NULL;

    if (!PyArg_ParseTuple(args, "s*O", &input, &py_previousCrc)) {
        return NULL;
    }

    /* Note: PyArg_ParseTuple() doesn't do overflow checking on unsigned values
     * so use PyLong_AsUnsignedLong() to get the value of the previousCrc arg */
    uint32_t previousCrc = PyLong_AsUnsignedLong(py_previousCrc);

    if (previousCrc == (uint32_t)-1 && PyErr_Occurred()) {
        goto done;
    }

    if (!PyBuffer_IsContiguous(&input, 'C')) {
        PyErr_SetString(PyExc_ValueError, "input must be contiguous buffer");
        goto done;
    }

    uint32_t val = previousCrc;

    /* Releasing the GIL for very small buffers is inefficient
       and may lower performance */
    if (input.len > 1024 * 5) {
        unsigned char *buf = input.buf;
        Py_ssize_t len = input.len;

        /* clang-format off */
        Py_BEGIN_ALLOW_THREADS
            /* Avoid truncation of length for very large buffers. crc() takes
               length as an int, which may be narrower than Py_ssize_t. */
            while ((size_t)len > INT_MAX) {
                val = checksum_fn(buf, INT_MAX, val);
                buf += (size_t)INT_MAX;
                len -= (size_t)INT_MAX;
            }
            val = checksum_fn(buf, (int)len, val);
        Py_END_ALLOW_THREADS
        /* clang-format on */
    } else {
        val = checksum_fn(input.buf, (int)input.len, val);
    }
    py_result = PyLong_FromUnsignedLong(val);
done:
    if (input.obj) {
        PyBuffer_Release(&input);
    }
    return py_result;
}

PyObject *aws_py_checksums_crc32(PyObject *self, PyObject *args) {
    (void)self;
    return checksums_crc_common(args, aws_checksums_crc32);
}

PyObject *aws_py_checksums_crc32c(PyObject *self, PyObject *args) {
    (void)self;
    return checksums_crc_common(args, aws_checksums_crc32c);
}
