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
#include <aws/io/socket.h>
#include <aws/io/tls_channel_handler.h>

#include <stdio.h>
#include <string.h>

const char *s_capsule_name_client_bootstrap = "aws_client_bootstrap";
static const char *s_capsule_name_elg = "aws_event_loop_group";
const char *s_capsule_name_host_resolver = "aws_host_resolver";
const char *s_capsule_name_tls_ctx = "aws_client_tls_ctx";
const char *s_capsule_name_tls_conn_options = "aws_tls_connection_options";

bool aws_py_socket_options_init(struct aws_socket_options *socket_options, PyObject *py_socket_options){
    AWS_ZERO_STRUCT(*socket_options);

    PyObject *sock_domain = PyObject_BorrowAttrString(py_socket_options, "domain");
    if (!PyIntEnum_Check(sock_domain)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.domain is invalid");
        goto error;
    }
    socket_options->domain = (enum aws_socket_domain)PyIntEnum_AsLong(sock_domain);

    PyObject *sock_type = PyObject_BorrowAttrString(py_socket_options, "type");
    if (!PyIntEnum_Check(sock_type)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.type is invalid");
        goto error;
    }
    socket_options->type = (enum aws_socket_type)PyIntEnum_AsLong(sock_type);

    PyObject *connect_timeout_ms = PyObject_BorrowAttrString(py_socket_options, "connect_timeout_ms");
    if (!PyLongOrInt_Check(connect_timeout_ms)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.connect_timeout_ms is invalid");
        goto error;
    }
    socket_options->connect_timeout_ms = (uint32_t)PyLong_AsLong(connect_timeout_ms);

    PyObject *keep_alive = PyObject_BorrowAttrString(py_socket_options, "keep_alive");
    if (!keep_alive) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive is invalid");
        goto error;
    }
    socket_options->keepalive = (bool)PyObject_IsTrue(keep_alive);

    PyObject *keep_alive_interval = PyObject_BorrowAttrString(py_socket_options, "keep_alive_interval_secs");
    if (!PyLongOrInt_Check(keep_alive_interval)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive_interval_secs is invalid");
        goto error;
    }
    socket_options->keep_alive_interval_sec = (uint16_t)PyLong_AsLong(keep_alive_interval);

    PyObject *keep_alive_timeout = PyObject_BorrowAttrString(py_socket_options, "keep_alive_timeout_secs");
    if (!PyLongOrInt_Check(keep_alive_timeout)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive_timeout_secs is invalid");
        goto error;
    }
    socket_options->keep_alive_timeout_sec = (uint16_t)PyLong_AsLong(keep_alive_timeout);

    PyObject *keep_alive_max_probes = PyObject_BorrowAttrString(py_socket_options, "keep_alive_max_probes");
    if (!PyLongOrInt_Check(keep_alive_timeout)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive_max_probes is invalid");
        goto error;
    }
    socket_options->keep_alive_max_failed_probes = (uint16_t)PyLong_AsLong(keep_alive_max_probes);

    return true;

error:
    AWS_ZERO_STRUCT(*socket_options);
    return false;
}

PyObject *aws_py_is_alpn_available(PyObject *self, PyObject *args) {

    (void)self;
    (void)args;

    return PyBool_FromLong(aws_tls_is_alpn_available());
}

static void s_elg_destructor(PyObject *elg_capsule) {
    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
    assert(elg);

    struct aws_allocator *allocator = elg->allocator;

    aws_event_loop_group_clean_up(elg);
    aws_mem_release(allocator, elg);
}

PyObject *aws_py_event_loop_group_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    uint16_t num_threads;
    if (!PyArg_ParseTuple(args, "H", &num_threads)) {
        return NULL;
    }

    struct aws_event_loop_group *elg = aws_mem_calloc(allocator, 1, sizeof(struct aws_event_loop_group));
    if (!elg) {
        return PyErr_AwsLastError();
    }

    if (aws_event_loop_group_default_init(elg, allocator, num_threads)) {
        PyErr_SetAwsLastError();
        goto elg_init_failed;
    }

    PyObject *capsule = PyCapsule_New(elg, s_capsule_name_elg, s_elg_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    return capsule;

capsule_new_failed:
    aws_event_loop_group_clean_up(elg);
elg_init_failed:
    aws_mem_release(allocator, elg);
    return NULL;
}

struct aws_event_loop_group *aws_py_get_event_loop_group(PyObject *event_loop_group) {
    struct aws_event_loop_group *native = NULL;

    PyObject *elg_capsule = PyObject_BorrowAttrString(event_loop_group, "_binding");
    if (elg_capsule) {
        native = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
        assert(native);
    }

    return native;
}

struct host_resolver_binding {
    struct aws_host_resolver native;

    /* Dependencies that must outlive this */
    PyObject *event_loop_group;
};

static void s_host_resolver_destructor(PyObject *host_resolver_capsule) {
    struct host_resolver_binding *host_resolver =
        PyCapsule_GetPointer(host_resolver_capsule, s_capsule_name_host_resolver);
    assert(host_resolver);
    aws_host_resolver_clean_up(&host_resolver->native);
    Py_DECREF(host_resolver->event_loop_group);
    aws_mem_release(aws_py_get_allocator(), host_resolver);
}

PyObject *aws_py_host_resolver_new_default(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    Py_ssize_t max_hosts;
    PyObject *elg_py;
    if (!PyArg_ParseTuple(args, "nO", &max_hosts, &elg_py)) {
        return NULL;
    }

    if (max_hosts < 1) {
        PyErr_SetString(PyExc_ValueError, "max_hosts must be greater than 0");
        return NULL;
    }

    struct aws_event_loop_group *elg = aws_py_get_event_loop_group(elg_py);
    if (!elg) {
        return NULL;
    }

    struct host_resolver_binding *host_resolver = aws_mem_calloc(allocator, 1, sizeof(struct host_resolver_binding));
    if (!host_resolver) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    if (aws_host_resolver_init_default(&host_resolver->native, allocator, max_hosts, elg)) {
        PyErr_SetAwsLastError();
        goto resolver_init_failed;
    }

    PyObject *capsule = PyCapsule_New(host_resolver, s_capsule_name_host_resolver, s_host_resolver_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    /* From hereon, nothing will fail */

    host_resolver->event_loop_group = elg_py;
    Py_INCREF(elg_py);
    return capsule;

capsule_new_failed:
    aws_host_resolver_clean_up(&host_resolver->native);
resolver_init_failed:
    aws_mem_release(allocator, host_resolver);
    return NULL;
}

struct aws_host_resolver *aws_py_get_host_resolver(PyObject *host_resolver) {
    struct aws_host_resolver *native = NULL;

    PyObject *binding_capsule = PyObject_BorrowAttrString(host_resolver, "_binding");
    if (binding_capsule) {
        struct host_resolver_binding *binding = PyCapsule_GetPointer(binding_capsule, s_capsule_name_host_resolver);
        if (binding) {
            native = &binding->native;
            assert(native);
        }
    }

    return native;
}

struct client_bootstrap_binding {
    struct aws_client_bootstrap *native;

    /* Dependencies that must outlive this */
    PyObject *event_loop_group;
    PyObject *host_resolver;
};

static void s_client_bootstrap_destructor(PyObject *bootstrap_capsule) {
    struct client_bootstrap_binding *bootstrap =
        PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_client_bootstrap);
    assert(bootstrap);
    Py_DECREF(bootstrap->host_resolver);
    Py_DECREF(bootstrap->event_loop_group);
    aws_client_bootstrap_release(bootstrap->native);
    aws_mem_release(aws_py_get_allocator(), bootstrap);
}

PyObject *aws_py_client_bootstrap_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *elg_py;
    PyObject *host_resolver_py;

    if (!PyArg_ParseTuple(args, "OO", &elg_py, &host_resolver_py)) {
        return NULL;
    }

    struct aws_event_loop_group *elg = aws_py_get_event_loop_group(elg_py);
    if (!elg) {
        return NULL;
    }

    struct aws_host_resolver *host_resolver = aws_py_get_host_resolver(host_resolver_py);
    if (!host_resolver) {
        return NULL;
    }

    struct client_bootstrap_binding *bootstrap = aws_mem_calloc(allocator, 1, sizeof(struct client_bootstrap_binding));
    if (!bootstrap) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    bootstrap->native = aws_client_bootstrap_new(allocator, elg, host_resolver, NULL);
    if (!bootstrap->native) {
        PyErr_SetAwsLastError();
        goto bootstrap_new_failed;
    }

    PyObject *capsule = PyCapsule_New(bootstrap, s_capsule_name_client_bootstrap, s_client_bootstrap_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    /* From hereon, nothing will fail */

    bootstrap->event_loop_group = elg_py;
    Py_INCREF(elg_py);

    bootstrap->host_resolver = host_resolver_py;
    Py_INCREF(host_resolver_py);

    return capsule;

capsule_new_failed:
    aws_client_bootstrap_release(bootstrap->native);
bootstrap_new_failed:
    aws_mem_release(allocator, bootstrap);
    return NULL;
}

struct aws_client_bootstrap *aws_py_get_client_bootstrap(PyObject *client_bootstrap) {
    struct aws_client_bootstrap *native = NULL;

    PyObject *binding_capsule = PyObject_BorrowAttrString(client_bootstrap, "_binding");
    if (binding_capsule) {
        struct client_bootstrap_binding *binding =
            PyCapsule_GetPointer(binding_capsule, s_capsule_name_client_bootstrap);
        if (binding) {
            native = binding->native;
            assert(native);
        }
    }

    return native;
}

static void s_tls_ctx_destructor(PyObject *tls_ctx_capsule) {

    struct aws_tls_ctx *tls_ctx = PyCapsule_GetPointer(tls_ctx_capsule, s_capsule_name_tls_ctx);
    assert(tls_ctx);

    aws_tls_ctx_destroy(tls_ctx);
}

PyObject *aws_py_client_tls_ctx_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    int min_tls_version;
    const char *ca_path;
    const char *ca_buffer;
    Py_ssize_t ca_buffer_len;
    const char *alpn_list;
    const char *certificate_buffer;
    Py_ssize_t certificate_buffer_len;
    const char *private_key_buffer;
    Py_ssize_t private_key_buffer_len;
    const char *pkcs12_path;
    const char *pkcs12_password;
    uint8_t verify_peer;
    if (!PyArg_ParseTuple(
            args,
            "bzz#zz#z#zzb",
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
    if (certificate_buffer_len > 0 && private_key_buffer_len > 0) {
        struct aws_byte_cursor cert = aws_byte_cursor_from_array(certificate_buffer, certificate_buffer_len);
        struct aws_byte_cursor key = aws_byte_cursor_from_array(private_key_buffer, private_key_buffer_len);
        if (aws_tls_ctx_options_init_client_mtls(&ctx_options, allocator, &cert, &key)) {
            PyErr_SetAwsLastError();
            return NULL;
        }
    } else {
        aws_tls_ctx_options_init_default_client(&ctx_options, allocator);
    }

    /* From hereon, we need to clean up if errors occur */

    ctx_options.minimum_tls_version = min_tls_version;

    if (ca_path) {
        if (aws_tls_ctx_options_override_default_trust_store_from_path(&ctx_options, ca_path, NULL)) {
            PyErr_SetAwsLastError();
            goto ctx_options_failure;
        }
    }
    if (ca_buffer_len > 0) {
        struct aws_byte_cursor ca = aws_byte_cursor_from_array(ca_buffer, ca_buffer_len);

        if (aws_tls_ctx_options_override_default_trust_store(&ctx_options, &ca)) {
            PyErr_SetAwsLastError();
            goto ctx_options_failure;
        }
    }

    if (alpn_list) {
        if (aws_tls_ctx_options_set_alpn_list(&ctx_options, alpn_list)) {
            PyErr_SetAwsLastError();
            goto ctx_options_failure;
        }
    }

#ifdef __APPLE__
    if (pkcs12_path && pkcs12_password) {
        struct aws_byte_cursor password = aws_byte_cursor_from_c_str(pkcs12_password);
        if (aws_tls_ctx_options_init_client_mtls_pkcs12_from_path(&ctx_options, allocator, pkcs12_path, &password)) {
            PyErr_SetAwsLastError();
            goto ctx_options_failure;
        }
    }
#endif
    ctx_options.verify_peer = (bool)verify_peer;
    struct aws_tls_ctx *tls_ctx = aws_tls_client_ctx_new(allocator, &ctx_options);
    if (!tls_ctx) {
        PyErr_SetAwsLastError();
        goto ctx_options_failure;
    }

    PyObject *capsule = PyCapsule_New(tls_ctx, s_capsule_name_tls_ctx, s_tls_ctx_destructor);
    if (!capsule) {
        goto capsule_new_failure;
    }

    /* From hereon, nothing will fail */

    aws_tls_ctx_options_clean_up(&ctx_options);
    return capsule;

capsule_new_failure:
ctx_options_failure:
    aws_tls_ctx_options_clean_up(&ctx_options);
    return NULL;
}

struct aws_tls_ctx *aws_py_get_tls_ctx(PyObject *tls_ctx) {
    struct aws_tls_ctx *native = NULL;

    PyObject *capsule = PyObject_BorrowAttrString(tls_ctx, "_binding");
    if (capsule) {
        native = PyCapsule_GetPointer(capsule, s_capsule_name_tls_ctx);
        assert(native);
    }

    return native;
}

struct tls_connection_options_binding {
    struct aws_tls_connection_options native;

    /* Dependencies that must outlive this */
    PyObject *tls_ctx;
};

static void s_tls_connection_options_destructor(PyObject *tls_connection_options_capsule) {

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct tls_connection_options_binding *tls_connection_options =
        PyCapsule_GetPointer(tls_connection_options_capsule, s_capsule_name_tls_conn_options);
    assert(tls_connection_options);

    aws_tls_connection_options_clean_up(&tls_connection_options->native);
    Py_DECREF(tls_connection_options->tls_ctx);
    aws_mem_release(allocator, tls_connection_options);
}

PyObject *aws_py_tls_connections_options_new_from_ctx(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *tls_ctx_py;

    if (!PyArg_ParseTuple(args, "O", &tls_ctx_py)) {
        return NULL;
    }

    struct aws_tls_ctx *ctx = aws_py_get_tls_ctx(tls_ctx_py);
    if (!ctx) {
        return NULL;
    }

    struct tls_connection_options_binding *conn_options =
        aws_mem_calloc(allocator, 1, sizeof(struct tls_connection_options_binding));
    if (!conn_options) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    PyObject *capsule =
        PyCapsule_New(conn_options, s_capsule_name_tls_conn_options, s_tls_connection_options_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    /* From hereon, nothing will fail */

    aws_tls_connection_options_init_from_ctx(&conn_options->native, ctx);

    conn_options->tls_ctx = tls_ctx_py;
    Py_INCREF(tls_ctx_py);

    return capsule;

capsule_new_failed:
    aws_mem_release(allocator, conn_options);
    return NULL;
}

struct aws_tls_connection_options *aws_py_get_tls_connection_options(PyObject *tls_connection_options) {
    struct aws_tls_connection_options *native = NULL;

    PyObject *binding_capsule = PyObject_BorrowAttrString(tls_connection_options, "_binding");
    if (binding_capsule) {
        struct tls_connection_options_binding *binding =
            PyCapsule_GetPointer(binding_capsule, s_capsule_name_tls_conn_options);
        if (binding) {
            native = &binding->native;
            assert(native);
        }
    }

    return native;
}

PyObject *aws_py_tls_connection_options_set_alpn_list(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *tls_conn_options_py;
    const char *alpn_list;
    if (!PyArg_ParseTuple(args, "Os", &tls_conn_options_py, &alpn_list)) {
        return NULL;
    }

    struct aws_tls_connection_options *connection_options = aws_py_get_tls_connection_options(tls_conn_options_py);
    if (!connection_options) {
        return NULL;
    }

    if (aws_tls_connection_options_set_alpn_list(connection_options, allocator, alpn_list)) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_tls_connection_options_set_server_name(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *tls_conn_options_py;
    const char *server_name;
    Py_ssize_t server_name_len;
    if (!PyArg_ParseTuple(args, "Os#", &tls_conn_options_py, &server_name, &server_name_len)) {
        return NULL;
    }

    struct aws_tls_connection_options *connection_options = aws_py_get_tls_connection_options(tls_conn_options_py);
    if (!connection_options) {
        return NULL;
    }

    struct aws_byte_cursor server_name_cur = aws_byte_cursor_from_array(server_name, (size_t)server_name_len);

    if (aws_tls_connection_options_set_server_name(connection_options, allocator, &server_name_cur)) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    Py_RETURN_NONE;
}
