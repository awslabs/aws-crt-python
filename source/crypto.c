/*
 * Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *  http://aws.amazon.com/apache2.0
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

#include "crypto.h"

#include "aws/cal/aws_hash.h"

const char *s_capsule_name_hash = "aws_hash";
const char *s_capsule_name_hmac = "aws_hmac";

static void s_hash_destructor(PyObject *hash_capsule) {
    assert(PyCapsule_CheckExact(hash_capsule));

    struct aws_hash *hash = PyCapsule_GetPointer(hash_capsule, s_capsule_name_hash);
    assert(hash);

    aws_hash_destory(hash);
}

static void s_hmac_destructor(PyObject *hmac_capsule) {
    assert(PyCapsule_CheckExact(hash_capsule));

    struct aws_hmac *hmac = PyCapsule_GetPointer(hmac_capsule, s_capsule_name_hmac);
    assert(hmac);

    aws_hash_destory(hmac);
}

PyObject *aws_py_sha256_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    struct aws_hash *sha256 = aws_sha256_new(allocator);

    if (!sha256) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    return PyCapsule_New(sha256, s_capsule_name_hash, s_hash_destructor);
}

PyObject *aws_py_md5_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    struct aws_hash *md5 = aws_md5_new(allocator);

    if (!md5) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    return PyCapsule_New(md5, s_capsule_name_hash, s_hash_destructor);
}

PyObject *aws_py_hash_update(PyObject *self, PyObject *args) {
    PyObject *hash_capsule = NULL;
    Py_buffer to_hash_stack;

    if (!PyArg_ParseTuple(args, "Os", &hash_capsule, &to_hash_stack)) {
        return Py_RETURN_NONE;
    }

    struct aws_hash *hash = PyCapsule_GetPointer(hash_capsule, s_capsule_name_hash);
    if (!hash) {
        return Py_RETURN_NONE;
    }

    struct aws_byte_cursor to_hash_cursor;
    to_hash_cursor = aws_byte_cursor_from_array(to_hash_stack.buf, to_hash_stack.len);

    if (aws_hash_update(hash, &to_hash_cursor)) {
        return Py_RETURN_NONE;
    }

    return Py_RETURN_NONE;
}

PyObject *aws_py_hash_digest(PyObject *self, PyObject *args) {
    PyObject *hash_capsule = NULL;

    if (!PyArg_ParseTuple(args, "O", &hash_capsule)) {
        return Py_RETURN_NONE;
    }

    struct aws_hash *hash = PyCapsule_GetPointer(hash_capsule, s_capsule_name_hash);
    if (!hash) {
        return Py_RETURN_NONE;
    }

    Py_buffer digest_data = 
    struct aws_byte_buf digest_buf = aws_byte_buf_from_array(buf, sizeof(buf));
    to_hash_cursor = aws_byte_cursor_from_array(to_hash_stack.buf, to_hash_stack.len);

    if (aws_hash_update(hash, &to_hash_cursor)) {
        return Py_RETURN_NONE;
    }

    return Py_RETURN_NONE;
}

PyObject *aws_py_sha256_hmac_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    struct aws_hmac *sha256_hmac = aws_sha256_hmac_new(allocator);

    if (!sha256_hmac) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    return PyCapsule_New(sha256_hmac, s_capsule_name_hmac, s_hmac_destructor);
}

