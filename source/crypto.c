/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "crypto.h"

#include "aws/cal/ecc.h"
#include "aws/cal/ed25519.h"
#include "aws/cal/hash.h"
#include "aws/cal/hmac.h"
#include "aws/cal/rsa.h"
#include "aws/common/encoding.h"
#include "aws/io/pem.h"

const char *s_capsule_name_hash = "aws_hash";
const char *s_capsule_name_hmac = "aws_hmac";
const char *s_capsule_name_rsa = "aws_rsa";
const char *s_capsule_name_ed25519 = "aws_ed25519";
const char *s_capsule_name_ec = "aws_ec";

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
    struct aws_rsa_key_pair *key_pair = NULL;

    if (found_pem_object != NULL) {
        key_pair =
            aws_rsa_key_pair_new_from_private_key_pkcs1(allocator, aws_byte_cursor_from_buf(&found_pem_object->data));
    } else {
        found_pem_object = s_find_pem_object(&pem_list, AWS_PEM_TYPE_PRIVATE_PKCS8);
        if (found_pem_object != NULL) {
            key_pair = aws_rsa_key_pair_new_from_private_key_pkcs8(
                allocator, aws_byte_cursor_from_buf(&found_pem_object->data));
        } else {
            PyErr_SetString(PyExc_ValueError, "RSA private key not found in PEM.");
            goto on_done;
        }
    }

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

PyObject *aws_py_rsa_private_key_from_der_data(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor der_data_cur;
    if (!PyArg_ParseTuple(args, "y#", &der_data_cur.ptr, &der_data_cur.len)) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_rsa_key_pair *key_pair = aws_rsa_key_pair_new_from_private_key_pkcs1(allocator, der_data_cur);

    if (key_pair == NULL) {
        PyErr_AwsLastError();
        goto on_done;
    }

    capsule = PyCapsule_New(key_pair, s_capsule_name_rsa, s_rsa_destructor);

    if (capsule == NULL) {
        aws_rsa_key_pair_release(key_pair);
    }

on_done:
    return capsule;
}

PyObject *aws_py_rsa_public_key_from_der_data(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor der_data_cur;
    if (!PyArg_ParseTuple(args, "y#", &der_data_cur.ptr, &der_data_cur.len)) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_rsa_key_pair *key_pair = aws_rsa_key_pair_new_from_public_key_pkcs1(allocator, der_data_cur);

    if (key_pair == NULL) {
        PyErr_AwsLastError();
        goto on_done;
    }

    capsule = PyCapsule_New(key_pair, s_capsule_name_rsa, s_rsa_destructor);

    if (capsule == NULL) {
        aws_rsa_key_pair_release(key_pair);
    }

on_done:
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

static void s_ed25519_destructor(PyObject *ed25519_capsule) {
    struct aws_ed25519_key_pair *key_pair = PyCapsule_GetPointer(ed25519_capsule, s_capsule_name_ed25519);
    assert(key_pair);

    aws_ed25519_key_pair_release(key_pair);
}

PyObject *aws_py_ed25519_new_generate(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_ed25519_key_pair *key_pair = aws_ed25519_key_pair_new_generate(allocator);

    if (key_pair == NULL) {
        PyErr_AwsLastError();
        goto on_done;
    }

    capsule = PyCapsule_New(key_pair, s_capsule_name_ed25519, s_ed25519_destructor);

    if (capsule == NULL) {
        aws_ed25519_key_pair_release(key_pair);
    }

on_done:
    return capsule;
}

PyObject *aws_py_ed25519_export_public_key(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *ed25519_capsule = NULL;
    int export_format = 0;

    if (!PyArg_ParseTuple(args, "Oi", &ed25519_capsule, &export_format)) {
        return NULL;
    }

    struct aws_ed25519_key_pair *ed25519 = PyCapsule_GetPointer(ed25519_capsule, s_capsule_name_ed25519);
    if (ed25519 == NULL) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_buf result_buf;
    aws_byte_buf_init(&result_buf, allocator, aws_ed25519_key_pair_get_public_key_size(export_format));

    if (aws_ed25519_key_pair_get_public_key(ed25519, export_format, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;
}

PyObject *aws_py_ed25519_export_private_key(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *ed25519_capsule = NULL;
    int export_format = 0;

    if (!PyArg_ParseTuple(args, "Oi", &ed25519_capsule, &export_format)) {
        return NULL;
    }

    struct aws_ed25519_key_pair *ed25519 = PyCapsule_GetPointer(ed25519_capsule, s_capsule_name_ed25519);
    if (ed25519 == NULL) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_buf result_buf;
    aws_byte_buf_init(&result_buf, allocator, aws_ed25519_key_pair_get_private_key_size(export_format));

    if (aws_ed25519_key_pair_get_private_key(ed25519, export_format, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;
}

static void s_ec_destructor(PyObject *ec_capsule) {
    struct aws_ecc_key_pair *key_pair = PyCapsule_GetPointer(ec_capsule, s_capsule_name_ec);
    assert(key_pair);

    aws_ecc_key_pair_release(key_pair);
}

PyObject *aws_py_ec_new_generate(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    int ec_type = 0;
    if (!PyArg_ParseTuple(args, "i", &ec_type)) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_ecc_key_pair *key_pair = aws_ecc_key_pair_new_generate_random(allocator, ec_type);

    if (key_pair == NULL) {
        return PyErr_AwsLastError();
    }

    capsule = PyCapsule_New(key_pair, s_capsule_name_ec, s_ec_destructor);

    if (capsule == NULL) {
        aws_ecc_key_pair_release(key_pair);
    }

    return capsule;
}

PyObject *aws_py_ec_key_from_der_data(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor der_data_cur;
    if (!PyArg_ParseTuple(args, "y#", &der_data_cur.ptr, &der_data_cur.len)) {
        return NULL;
    }

    PyObject *capsule = NULL;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_ecc_key_pair *key_pair = aws_ecc_key_pair_new_from_asn1(allocator, &der_data_cur);

    if (key_pair == NULL) {
        PyErr_AwsLastError();
        goto on_done;
    }

    capsule = PyCapsule_New(key_pair, s_capsule_name_rsa, s_ec_destructor);

    if (capsule == NULL) {
        aws_ecc_key_pair_release(key_pair);
    }

on_done:
    return capsule;
}

PyObject *aws_py_ec_export_key(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *ec_capsule = NULL;
    int export_format = 0;

    if (!PyArg_ParseTuple(args, "Oi", &ec_capsule, &export_format)) {
        return NULL;
    }

    struct aws_ecc_key_pair *ec = PyCapsule_GetPointer(ec_capsule, s_capsule_name_ec);
    if (ec == NULL) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_buf result_buf;
    /* all current curves max out at around 200 bytes in pkcs8, */
    aws_byte_buf_init(&result_buf, allocator, 512);

    if (aws_ecc_key_pair_export(ec, export_format, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;
}

PyObject *aws_py_ec_sign(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();
    PyObject *ec_capsule = NULL;
    struct aws_byte_cursor digest_cur;
    if (!PyArg_ParseTuple(args, "Oy#", &ec_capsule, &digest_cur.ptr, &digest_cur.len)) {
        return NULL;
    }

    struct aws_ecc_key_pair *ec = PyCapsule_GetPointer(ec_capsule, s_capsule_name_ec);
    if (ec == NULL) {
        return NULL;
    }

    struct aws_byte_buf result_buf;
    aws_byte_buf_init(&result_buf, allocator, aws_ecc_key_pair_signature_length(ec));

    if (aws_ecc_key_pair_sign_message(ec, &digest_cur, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        return PyErr_AwsLastError();
    }

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;
}

PyObject *aws_py_ec_verify(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *ec_capsule = NULL;
    struct aws_byte_cursor digest_cur;
    struct aws_byte_cursor signature_cur;
    if (!PyArg_ParseTuple(
            args, "Oy#y#", &ec_capsule, &digest_cur.ptr, &digest_cur.len, &signature_cur.ptr, &signature_cur.len)) {
        return NULL;
    }

    struct aws_ecc_key_pair *ec = PyCapsule_GetPointer(ec_capsule, s_capsule_name_ec);
    if (ec == NULL) {
        return NULL;
    }

    if (aws_ecc_key_pair_verify_signature(ec, &digest_cur, &signature_cur)) {
        if (aws_last_error() == AWS_ERROR_CAL_SIGNATURE_VALIDATION_FAILED) {
            aws_reset_error();
            Py_RETURN_FALSE;
        }
        return PyErr_AwsLastError();
    }

    Py_RETURN_TRUE;
}

PyObject *aws_py_ec_encode_signature(PyObject *self, PyObject *args) {

    PyObject *signature;
    PyObject *r_bytes;
    PyObject *s_bytes;

    if (!PyArg_ParseTuple(args, "O", &signature))
        return NULL;

    r_bytes = PyObject_GetAttrString(signature, "r");
    if (!r_bytes)
        return NULL;

    s_bytes = PyObject_GetAttrString(signature, "s");
    if (!s_bytes) {
        Py_DECREF(r_bytes);
        return NULL;
    }

    if (!PyBytes_Check(r_bytes) || !PyBytes_Check(s_bytes)) {
        PyErr_SetString(PyExc_TypeError, "r and s must be bytes");
        Py_DECREF(r_bytes);
        Py_DECREF(s_bytes);
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_byte_cursor r_cur = aws_byte_cursor_from_pybytes(r_bytes);
    struct aws_byte_cursor s_cur = aws_byte_cursor_from_pybytes(s_bytes);

    size_t buf_size = r_cur.len + s_cur.len + 32; /* der has static overhead of couple bytes, just overallocate */
    if (buf_size > 256) {
        aws_raise_error(AWS_ERROR_INVALID_ARGUMENT);
        goto on_error;
    }

    struct aws_byte_buf result_buf;
    aws_byte_buf_init(&result_buf, allocator, buf_size);

    if (aws_ecc_encode_signature_raw_to_der(allocator, r_cur, s_cur, &result_buf)) {
        aws_byte_buf_clean_up_secure(&result_buf);
        goto on_error;
    }

    Py_DECREF(r_bytes);
    Py_DECREF(s_bytes);

    PyObject *ret = PyBytes_FromStringAndSize((const char *)result_buf.buffer, result_buf.len);
    aws_byte_buf_clean_up_secure(&result_buf);
    return ret;

on_error:
    Py_DECREF(r_bytes);
    Py_DECREF(s_bytes);
    return PyErr_AwsLastError();
}

PyObject *aws_py_ec_decode_signature(PyObject *self, PyObject *args) {
    struct aws_byte_cursor signature_cur;
    if (!PyArg_ParseTuple(args, "s#", &signature_cur.ptr, &signature_cur.len)) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();
    struct aws_byte_cursor r_cur = {0};
    struct aws_byte_cursor s_cur = {0};
    if (aws_ecc_decode_signature_der_to_raw(allocator, signature_cur, &r_cur, &s_cur)) {
        return PyErr_AwsLastError();
    }

    PyObject *result = PyTuple_New(3);
    if (!result) {
        return NULL;
    }

    PyTuple_SET_ITEM(result, 0, PyBytes_FromStringAndSize(r_cur.ptr, r_cur.len));
    PyTuple_SET_ITEM(result, 1, PyBytes_FromStringAndSize(s_cur.ptr, s_cur.len));

    return result;
}
