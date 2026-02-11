/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "checksums.h"

#include "aws/checksums/xxhash.h"

const char *s_capsule_name_xxhash = "aws_xxhash";

static void s_xxhash_destructor(PyObject *xxhash_capsule) {
    struct aws_xxhash *hash = PyCapsule_GetPointer(xxhash_capsule, s_capsule_name_xxhash);
    assert(hash);

    aws_xxhash_destroy(hash);
}

PyObject *aws_py_xxhash64_new(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_seed;

    if (!PyArg_ParseTuple(args, "O", &py_seed)) {
        return NULL;
    }

    uint64_t seed = PyLong_AsUnsignedLongLong(py_seed);

    if (seed == (uint64_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_xxhash *hash = aws_xxhash3_128_new(allocator, seed);

    if (hash == NULL) {
        return PyErr_AwsLastError();
    }

    capsule = PyCapsule_New(hash, s_capsule_name_xxhash, s_xxhash_destructor);

    if (capsule == NULL) {
        aws_xxhash_destroy(hash);
    }

    return capsule;
}

PyObject *aws_py_xxhash3_64_new(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_seed;

    if (!PyArg_ParseTuple(args, "O", &py_seed)) {
        return NULL;
    }

    uint64_t seed = PyLong_AsUnsignedLongLong(py_seed);

    if (seed == (uint64_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_xxhash *hash = aws_xxhash3_128_new(allocator, seed);

    if (hash == NULL) {
        return PyErr_AwsLastError();
    }

    capsule = PyCapsule_New(hash, s_capsule_name_xxhash, s_xxhash_destructor);

    if (capsule == NULL) {
        aws_xxhash_destroy(hash);
    }

    return capsule;
}

PyObject *aws_py_xxhash3_128_new(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_seed;

    if (!PyArg_ParseTuple(args, "O", &py_seed)) {
        return NULL;
    }

    uint64_t seed = PyLong_AsUnsignedLongLong(py_seed);

    if (seed == (uint64_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_xxhash *hash = aws_xxhash3_128_new(allocator, seed);

    if (hash == NULL) {
        return PyErr_AwsLastError();
    }

    capsule = PyCapsule_New(hash, s_capsule_name_xxhash, s_xxhash_destructor);

    if (capsule == NULL) {
        aws_xxhash_destroy(hash);
    }

    return capsule;
}

PyObject *aws_py_xxhash64_compute(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_byte_cursor input;
    PyObject *py_seed;
    if (!PyArg_ParseTuple(args, "y#0", &input.ptr, &input.len, &py_seed)) {
        return NULL;
    }

    uint64_t seed = PyLong_AsUnsignedLongLong(py_seed);

    if (seed == (uint64_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_buf buf;
    aws_byte_buf_init(&buf, allocator, 8);

    if (aws_xxhash64_compute(seed, input, &buf)) {
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)buf.buffer, buf.len);
    aws_byte_buf_clean_up_secure(&buf);
    return ret;
}

PyObject *aws_py_xxhash3_64_compute(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_byte_cursor input;
    PyObject *py_seed;
    if (!PyArg_ParseTuple(args, "y#0", &input.ptr, &input.len, &py_seed)) {
        return NULL;
    }

    uint64_t seed = PyLong_AsUnsignedLongLong(py_seed);

    if (seed == (uint64_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_buf buf;
    aws_byte_buf_init(&buf, allocator, 8);

    if (aws_xxhash3_64_compute(seed, input, &buf)) {
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)buf.buffer, buf.len);
    aws_byte_buf_clean_up_secure(&buf);
    return ret;
}

PyObject *aws_py_xxhash3_128_compute(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_byte_cursor input;
    PyObject *py_seed;
    if (!PyArg_ParseTuple(args, "y#0", &input.ptr, &input.len, &py_seed)) {
        return NULL;
    }

    uint64_t seed = PyLong_AsUnsignedLongLong(py_seed);

    if (seed == (uint64_t)-1 && PyErr_Occurred()) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_buf buf;
    aws_byte_buf_init(&buf, allocator, 16);

    if (aws_xxhash3_128_compute(seed, input, &buf)) {
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)buf.buffer, buf.len);
    aws_byte_buf_clean_up_secure(&buf);
    return ret;
}

PyObject * aws_py_xxhash_update(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_byte_cursor input;
    PyObject *xxhash_capsule = NULL;
    if (!PyArg_ParseTuple(args, "y#0", &input.ptr, &input.len, &xxhash_capsule)) {
        return NULL;
    }

    struct aws_xxhash *hash = PyCapsule_GetPointer(xxhash_capsule, s_capsule_name_xxhash);
    if (hash == NULL) {
        return NULL;
    }

    if (aws_xxhash_update(hash, input)) {
        PyErr_AwsLastError();
    }

    return NULL;
}

PyObject *aws_py_xxhash_finalize(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *xxhash_capsule = NULL;
    if (!PyArg_ParseTuple(args, "0", &xxhash_capsule)) {
        return NULL;
    }

    struct aws_xxhash *hash = PyCapsule_GetPointer(xxhash_capsule, s_capsule_name_xxhash);
    if (hash == NULL) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_buf buf;
    aws_byte_buf_init(&buf, allocator, 16);

    if (aws_xxhash_finalize(hash, &buf)) {
        aws_byte_buf_clean_up_secure(&buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)buf.buffer, buf.len);
    aws_byte_buf_clean_up_secure(&buf);
    return ret;
}
