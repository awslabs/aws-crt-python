/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "crypto.h"

#include "aws/cal/hash.h"
#include "aws/cal/hmac.h"

const char *s_capsule_name_hash = "aws_hash";
const char *s_capsule_name_hmac = "aws_hmac";

static void s_hash_destructor(PyObject *hash_capsule) {
    assert(PyCapsule_CheckExact(hash_capsule));

    struct aws_hash *hash = PyCapsule_GetPointer(hash_capsule, s_capsule_name_hash);
    assert(hash);

    aws_hash_destroy(hash);
}

static void s_hmac_destructor(PyObject *hmac_capsule) {
    assert(PyCapsule_CheckExact(hmac_capsule));

    struct aws_hmac *hmac = PyCapsule_GetPointer(hmac_capsule, s_capsule_name_hmac);
    assert(hmac);

    aws_hmac_destroy(hmac);
}

PyObject *aws_py_sha256_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_hash *sha256 = aws_sha256_new(allocator);

    if (!sha256) {
        return PyErr_AwsLastError();
    }

    return PyCapsule_New(sha256, s_capsule_name_hash, s_hash_destructor);
}

PyObject *aws_py_md5_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_hash *md5 = aws_md5_new(allocator);

    if (!md5) {
        return PyErr_AwsLastError();
    }

    return PyCapsule_New(md5, s_capsule_name_hash, s_hash_destructor);
}

PyObject *aws_py_hash_update(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *hash_capsule = NULL;
    const char *to_hash_c_str;
    Py_ssize_t to_hash_len;

    if (!PyArg_ParseTuple(args, "Os#", &hash_capsule, &to_hash_c_str, &to_hash_len)) {
        return PyErr_AwsLastError();
    }

    struct aws_hash *hash = PyCapsule_GetPointer(hash_capsule, s_capsule_name_hash);
    if (!hash) {
        return PyErr_AwsLastError();
    }

    struct aws_byte_cursor to_hash_cursor;
    to_hash_cursor = aws_byte_cursor_from_array(to_hash_c_str, to_hash_len);

    if (aws_hash_update(hash, &to_hash_cursor)) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_hash_digest(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *hash_capsule = NULL;
    Py_ssize_t truncate_to;

    if (!PyArg_ParseTuple(args, "On", &hash_capsule, &truncate_to)) {
        return PyErr_AwsLastError();
    }

    struct aws_hash *hash = PyCapsule_GetPointer(hash_capsule, s_capsule_name_hash);
    if (!hash) {
        return PyErr_AwsLastError();
    }

    uint8_t output[128] = {0};
    struct aws_byte_buf digest_buf = aws_byte_buf_from_array(output, hash->digest_size);
    digest_buf.len = 0;

    if (aws_hash_finalize(hash, &digest_buf, truncate_to)) {
        return PyErr_AwsLastError();
    }

    return PyBytes_FromStringAndSize((const char *)output, digest_buf.len);
}

PyObject *aws_py_sha256_hmac_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    const char *secret_ptr;
    Py_ssize_t secret_len;

    if (!PyArg_ParseTuple(args, "s#", &secret_ptr, &secret_len)) {
        return PyErr_AwsLastError();
    }

    struct aws_byte_cursor secret_cursor;
    secret_cursor = aws_byte_cursor_from_array(secret_ptr, secret_len);

    struct aws_hmac *sha256_hmac = aws_sha256_hmac_new(allocator, &secret_cursor);

    if (!sha256_hmac) {
        return PyErr_AwsLastError();
    }

    return PyCapsule_New(sha256_hmac, s_capsule_name_hmac, s_hmac_destructor);
}

PyObject *aws_py_hmac_update(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *hmac_capsule = NULL;
    const char *to_hmac_ptr;
    Py_ssize_t to_hmac_len;

    if (!PyArg_ParseTuple(args, "Os#", &hmac_capsule, &to_hmac_ptr, &to_hmac_len)) {
        return PyErr_AwsLastError();
    }

    struct aws_hmac *hmac = PyCapsule_GetPointer(hmac_capsule, s_capsule_name_hmac);
    if (!hmac) {
        return PyErr_AwsLastError();
    }

    struct aws_byte_cursor to_hmac_cursor;
    to_hmac_cursor = aws_byte_cursor_from_array(to_hmac_ptr, to_hmac_len);

    if (aws_hmac_update(hmac, &to_hmac_cursor)) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_hmac_digest(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *hmac_capsule = NULL;
    Py_ssize_t truncate_to;

    if (!PyArg_ParseTuple(args, "On", &hmac_capsule, &truncate_to)) {
        return PyErr_AwsLastError();
    }

    struct aws_hmac *hmac = PyCapsule_GetPointer(hmac_capsule, s_capsule_name_hmac);
    if (!hmac) {
        return PyErr_AwsLastError();
    }

    uint8_t output[128] = {0};
    struct aws_byte_buf digest_buf = aws_byte_buf_from_array(output, hmac->digest_size);
    digest_buf.len = 0;

    if (aws_hmac_finalize(hmac, &digest_buf, truncate_to)) {
        return PyErr_AwsLastError();
    }

    return PyBytes_FromStringAndSize((const char *)output, digest_buf.len);
}
