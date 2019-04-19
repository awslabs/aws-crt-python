/*
 * Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
#include "io.h"

#include <aws/io/channel_bootstrap.h>
#include <aws/io/event_loop.h>
#include <aws/io/tls_channel_handler.h>

const char *s_capsule_name_client_bootstrap = "aws_client_bootstrap";
static const char *s_capsule_name_elg = "aws_event_loop_group";
const char *s_capsule_name_host_resolver = "aws_host_resolver";
const char *s_capsule_name_tls_ctx = "aws_client_tls_ctx";

PyObject *aws_py_is_alpn_available(PyObject *self, PyObject *args) {

    (void)self;
    (void)args;

    return PyBool_FromLong(aws_tls_is_alpn_available());
}

static void s_elg_destructor(PyObject *elg_capsule) {

    assert(PyCapsule_CheckExact(elg_capsule));

    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
    assert(elg);

    struct aws_allocator *allocator = elg->allocator;

    aws_event_loop_group_clean_up(elg);
    aws_mem_release(allocator, elg);
}

PyObject *aws_py_io_event_loop_group_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    uint16_t num_threads = 0;

    if (!PyArg_ParseTuple(args, "H", &num_threads)) {
        return NULL;
    }

    struct aws_event_loop_group *elg = aws_mem_acquire(allocator, sizeof(struct aws_event_loop_group));
    if (!elg) {
        return PyErr_AwsLastError();
    }
    AWS_ZERO_STRUCT(*elg);

    if (aws_event_loop_group_default_init(elg, allocator, num_threads)) {
        aws_mem_release(allocator, elg);
        return PyErr_AwsLastError();
    }

    return PyCapsule_New(elg, s_capsule_name_elg, s_elg_destructor);
}

static void s_host_resolver_destructor(PyObject *host_resolver_capsule) {
    assert(PyCapsule_CheckExact(host_resolver_capsule));

    struct aws_host_resolver *host_resolver = PyCapsule_GetPointer(host_resolver_capsule, s_capsule_name_host_resolver);
    assert(host_resolver);
    aws_host_resolver_clean_up(host_resolver);
    aws_mem_release(aws_crt_python_get_allocator(), host_resolver);
}

PyObject *aws_py_io_host_resolver_new_default(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    int max_hosts = 16;
    PyObject *elg_capsule = NULL;
    if (!PyArg_ParseTuple(args, "bO", &max_hosts, &elg_capsule)) {
        return NULL;
    }
    if (!elg_capsule || !PyCapsule_CheckExact(elg_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }

    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
    struct aws_host_resolver *host_resolver = aws_mem_acquire(allocator, sizeof(struct aws_host_resolver));
    if (aws_host_resolver_init_default(host_resolver, allocator, max_hosts, elg)) {
        PyErr_SetAwsLastError();
        aws_mem_release(allocator, host_resolver);
        return NULL;
    }

    return PyCapsule_New(host_resolver, s_capsule_name_host_resolver, s_host_resolver_destructor);
}

static void s_client_bootstrap_destructor(PyObject *bootstrap_capsule) {

    assert(PyCapsule_CheckExact(bootstrap_capsule));

    struct aws_client_bootstrap *bootstrap = PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_client_bootstrap);
    assert(bootstrap);
    aws_client_bootstrap_release(bootstrap);
}

PyObject *aws_py_io_client_bootstrap_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    PyObject *elg_capsule = NULL;
    PyObject *host_resolver_capsule = NULL;

    if (!PyArg_ParseTuple(args, "OO", &elg_capsule, &host_resolver_capsule)) {
        return NULL;
    }

    if (!elg_capsule || !PyCapsule_CheckExact(elg_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }
    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
    if (!elg) {
        return NULL;
    }

    if (!host_resolver_capsule || !PyCapsule_CheckExact(host_resolver_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }
    struct aws_host_resolver *host_resolver = PyCapsule_GetPointer(host_resolver_capsule, s_capsule_name_host_resolver);

    struct aws_client_bootstrap *bootstrap = aws_client_bootstrap_new(allocator, elg, host_resolver, NULL);
    if (!bootstrap) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    return PyCapsule_New(bootstrap, s_capsule_name_client_bootstrap, s_client_bootstrap_destructor);
}

static void s_tls_ctx_destructor(PyObject *tls_ctx_capsule) {

    assert(PyCapsule_CheckExact(tls_ctx_capsule));

    struct aws_tls_ctx *tls_ctx = PyCapsule_GetPointer(tls_ctx_capsule, s_capsule_name_tls_ctx);
    assert(tls_ctx);

    aws_tls_ctx_destroy(tls_ctx);
}

PyObject *aws_py_io_client_tls_ctx_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    int min_tls_version = AWS_IO_TLS_VER_SYS_DEFAULTS;
    const char *ca_path = NULL;
    const char *ca_buffer = NULL;
    Py_ssize_t ca_buffer_len = 0;
    const char *alpn_list = NULL;
    const char *certificate_buffer = NULL;
    Py_ssize_t certificate_buffer_len = 0;
    const char *private_key_buffer = NULL;
    Py_ssize_t private_key_buffer_len = 0;
    const char *pkcs12_path = NULL;
    const char *pkcs12_password = NULL;
    PyObject *verify_peer = NULL;

    if (!PyArg_ParseTuple(
            args,
            "bzy#zy#y#zzO",
            &min_tls_version,
            &ca_path,
            &ca_buffer,
            &ca_buffer_len,
            &alpn_list,
            &certificate_buffer,
            &certificate_buffer_len,
            &private_key_buffer,
            &private_key_buffer_len,
            &pkcs12_path,
            &pkcs12_password,
            &verify_peer)) {
        return NULL;
    }

    struct aws_tls_ctx_options ctx_options;
    AWS_ZERO_STRUCT(ctx_options);
    if (certificate_buffer && private_key_buffer && 
        certificate_buffer_len > 0 && private_key_buffer_len > 0) {
        struct aws_byte_cursor cert = aws_byte_cursor_from_array(certificate_buffer, certificate_buffer_len);
        struct aws_byte_cursor key = aws_byte_cursor_from_array(private_key_buffer, private_key_buffer_len);
        aws_tls_ctx_options_init_client_mtls(&ctx_options, allocator, &cert, &key);
    } else {
        aws_tls_ctx_options_init_default_client(&ctx_options, allocator);
    }

    ctx_options.minimum_tls_version = min_tls_version;

    if (ca_path) {
        aws_tls_ctx_options_override_default_trust_store_from_path(&ctx_options, ca_path, NULL);
    } 
    if (ca_buffer && ca_buffer_len > 0) {
        struct aws_byte_cursor ca = aws_byte_cursor_from_array(ca_buffer, ca_buffer_len);
        aws_tls_ctx_options_override_default_trust_store(&ctx_options, &ca);
    }

    if (alpn_list) {
        aws_tls_ctx_options_set_alpn_list(&ctx_options, alpn_list);
    }

#ifdef __APPLE__
    if (pkcs12_path && pkcs12_password) {
        struct aws_byte_cursor password = aws_byte_cursor_from_c_str(pkcs12_password);
        aws_tls_ctx_options_init_client_mtls_pkcs12_from_path(&ctx_options, allocator, pkcs12_path, &password);
    }
#endif

    if (verify_peer != Py_None) {
        ctx_options.verify_peer = verify_peer == Py_True;
    }

    struct aws_tls_ctx *tls_ctx = aws_tls_client_ctx_new(allocator, &ctx_options);
    if (!tls_ctx) {
        return PyErr_AwsLastError();
    }

    return PyCapsule_New(tls_ctx, s_capsule_name_tls_ctx, s_tls_ctx_destructor);
}
