/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "crypto.h"

#include "aws/cal/hash.h"
#include "aws/cal/hmac.h"
#include "aws/cal/rsa.h"
#include "aws/io/pem.h"

const char *s_capsule_name_hash = "aws_hash";
const char *s_capsule_name_hmac = "aws_hmac";
const char *s_capsule_name_rsa = "aws_rsa";

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

PyObject *aws_py_sha1_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_hash *sha1 = aws_sha1_new(allocator);

    if (!sha1) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule = PyCapsule_New(sha1, s_capsule_name_hash, s_hash_destructor);

    if (capsule == NULL) {
        aws_hash_destroy(sha1);
        return NULL;
    }

    return capsule;
}

PyObject *aws_py_sha256_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_hash *sha256 = aws_sha256_new(allocator);

    if (!sha256) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule = PyCapsule_New(sha256, s_capsule_name_hash, s_hash_destructor);

    if (capsule == NULL) {
        aws_hash_destroy(sha256);
        return NULL;
    }

    return capsule;
}

PyObject *aws_py_md5_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_hash *md5 = aws_md5_new(allocator);

    if (!md5) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule = PyCapsule_New(md5, s_capsule_name_hash, s_hash_destructor);

    if (capsule == NULL) {
        aws_hash_destroy(md5);
        return NULL;
    }

    return capsule;
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

    /* Releasing the GIL for very small buffers is inefficient
       and may lower performance */
    if (to_hash_len > 1024 * 5) {
        int aws_op = AWS_OP_SUCCESS;

        /* clang-format off */
        Py_BEGIN_ALLOW_THREADS
            aws_op = aws_hash_update(hash, &to_hash_cursor);
        Py_END_ALLOW_THREADS

        if (aws_op != AWS_OP_SUCCESS) {
            return PyErr_AwsLastError();
        }
        /* clang-format on */
    } else {
        if (aws_hash_update(hash, &to_hash_cursor)) {
            return PyErr_AwsLastError();
        }
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

static void s_rsa_destructor(PyObject *rsa_capsule) {
    struct aws_rsa_key_pair *key_pair = PyCapsule_GetPointer(rsa_capsule, s_capsule_name_rsa);
    assert(key_pair);

    aws_rsa_key_pair_release(key_pair);
}

struct aws_pem_object *s_find_pem_object(struct aws_array_list *pem_list, enum aws_pem_object_type pem_type) {
    for (size_t i = 0; i < aws_array_list_length(pem_list); ++i) {
        struct aws_pem_object *pem_object = NULL;
        if (aws_array_list_get_at_ptr(pem_list, (void **)&pem_object, 0)) {
            return NULL;
        }

        if (pem_object->type == pem_type) {
            return pem_object;
        }
    }

    return NULL;
}

PyObject *aws_py_rsa_private_key_from_pem_data(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor pem_data_cur;
    if (!PyArg_ParseTuple(args, "s#", &pem_data_cur.ptr, &pem_data_cur.len)) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_array_list pem_list;
    if (aws_pem_objects_init_from_file_contents(&pem_list, allocator, pem_data_cur)) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur */

    struct aws_pem_object *found_pem_object = s_find_pem_object(&pem_list, AWS_PEM_TYPE_PRIVATE_RSA_PKCS1);

    if (found_pem_object == NULL) {
        PyErr_SetString(PyExc_ValueError, "RSA private key not found in PEM.");
        goto on_done;
    }

    struct aws_rsa_key_pair *key_pair =
        aws_rsa_key_pair_new_from_private_key_pkcs1(allocator, aws_byte_cursor_from_buf(&found_pem_object->data));

    if (key_pair == NULL) {
        PyErr_AwsLastError();
        goto on_done;
    }

    capsule = PyCapsule_New(key_pair, s_capsule_name_rsa, s_rsa_destructor);

    if (capsule == NULL) {
        aws_rsa_key_pair_release(key_pair);
    }

on_done:
    aws_pem_objects_clean_up(&pem_list);
    return capsule;
}

PyObject *aws_py_rsa_public_key_from_pem_data(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor pem_data_cur;
    if (!PyArg_ParseTuple(args, "s#", &pem_data_cur.ptr, &pem_data_cur.len)) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_array_list pem_list;
    if (aws_pem_objects_init_from_file_contents(&pem_list, allocator, pem_data_cur)) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur */

    struct aws_pem_object *found_pem_object = s_find_pem_object(&pem_list, AWS_PEM_TYPE_PUBLIC_RSA_PKCS1);

    if (found_pem_object == NULL) {
        PyErr_SetString(PyExc_ValueError, "RSA public key not found in PEM.");
        goto on_done;
    }

    struct aws_rsa_key_pair *key_pair =
        aws_rsa_key_pair_new_from_public_key_pkcs1(allocator, aws_byte_cursor_from_buf(&found_pem_object->data));

    if (key_pair == NULL) {
        PyErr_AwsLastError();
        goto on_done;
    }

    capsule = PyCapsule_New(key_pair, s_capsule_name_rsa, s_rsa_destructor);

    if (capsule == NULL) {
        aws_rsa_key_pair_release(key_pair);
    }

on_done:
    aws_pem_objects_clean_up(&pem_list);
    return capsule;
}

PyObject *aws_py_rsa_encrypt(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();
    PyObject *rsa_capsule = NULL;
    int encrypt_algo = 0;
    struct aws_byte_cursor plaintext_cur;
    if (!PyArg_ParseTuple(args, "Ois#", &rsa_capsule, &encrypt_algo, &plaintext_cur.ptr, &plaintext_cur.len)) {
        return NULL;
    }

    struct aws_rsa_key_pair *rsa = PyCapsule_GetPointer(rsa_capsule, s_capsule_name_rsa);
    if (rsa == NULL) {
        return NULL;
    }

    struct aws_byte_buf result_buf;
    aws_byte_buf_init(&result_buf, allocator, aws_rsa_key_pair_block_length(rsa));

    if (aws_rsa_key_pair_encrypt(rsa, encrypt_algo, plaintext_cur, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;
}

PyObject *aws_py_rsa_decrypt(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();
    PyObject *rsa_capsule = NULL;
    int encrypt_algo = 0;
    struct aws_byte_cursor ciphertext_cur;
    if (!PyArg_ParseTuple(args, "Oiy#", &rsa_capsule, &encrypt_algo, &ciphertext_cur.ptr, &ciphertext_cur.len)) {
        return NULL;
    }

    struct aws_rsa_key_pair *rsa = PyCapsule_GetPointer(rsa_capsule, s_capsule_name_rsa);
    if (rsa == NULL) {
        return NULL;
    }

    struct aws_byte_buf result_buf;
    aws_byte_buf_init(&result_buf, allocator, aws_rsa_key_pair_block_length(rsa));

    if (aws_rsa_key_pair_decrypt(rsa, encrypt_algo, ciphertext_cur, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;
}

PyObject *aws_py_rsa_sign(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();
    PyObject *rsa_capsule = NULL;
    int sign_algo = 0;
    struct aws_byte_cursor digest_cur;
    if (!PyArg_ParseTuple(args, "Oiy#", &rsa_capsule, &sign_algo, &digest_cur.ptr, &digest_cur.len)) {
        return NULL;
    }

    struct aws_rsa_key_pair *rsa = PyCapsule_GetPointer(rsa_capsule, s_capsule_name_rsa);
    if (rsa == NULL) {
        return NULL;
    }

    struct aws_byte_buf result_buf;
    aws_byte_buf_init(&result_buf, allocator, aws_rsa_key_pair_signature_length(rsa));

    if (aws_rsa_key_pair_sign_message(rsa, sign_algo, digest_cur, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;
}

PyObject *aws_py_rsa_verify(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *rsa_capsule = NULL;
    int sign_algo = 0;
    struct aws_byte_cursor digest_cur;
    struct aws_byte_cursor signature_cur;
    if (!PyArg_ParseTuple(
            args,
            "Oiy#y#",
            &rsa_capsule,
            &sign_algo,
            &digest_cur.ptr,
            &digest_cur.len,
            &signature_cur.ptr,
            &signature_cur.len)) {
        return NULL;
    }

    struct aws_rsa_key_pair *rsa = PyCapsule_GetPointer(rsa_capsule, s_capsule_name_rsa);
    if (rsa == NULL) {
        return NULL;
    }

    if (aws_rsa_key_pair_verify_signature(rsa, sign_algo, digest_cur, signature_cur)) {
        if (aws_last_error() == AWS_ERROR_CAL_SIGNATURE_VALIDATION_FAILED) {
            aws_reset_error();
            Py_RETURN_FALSE;
        }
        return PyErr_AwsLastError();
    }

    Py_RETURN_TRUE;
}
