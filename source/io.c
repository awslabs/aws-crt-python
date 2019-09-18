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
#include <aws/io/stream.h>
#include <aws/io/tls_channel_handler.h>

#include <stdio.h>
#include <string.h>

static const char *s_capsule_name_client_bootstrap = "aws_client_bootstrap";
static const char *s_capsule_name_elg = "aws_event_loop_group";
static const char *s_capsule_name_host_resolver = "aws_host_resolver";
static const char *s_capsule_name_tls_ctx = "aws_client_tls_ctx";
static const char *s_capsule_name_tls_conn_options = "aws_tls_connection_options";

bool aws_py_socket_options_init(struct aws_socket_options *socket_options, PyObject *py_socket_options) {
    AWS_ZERO_STRUCT(*socket_options);

    bool success = false;

    /* These references all need to be cleaned up before function returns */
    PyObject *sock_domain = NULL;
    PyObject *sock_type = NULL;
    PyObject *connect_timeout_ms = NULL;
    PyObject *keep_alive = NULL;
    PyObject *keep_alive_interval = NULL;
    PyObject *keep_alive_timeout = NULL;
    PyObject *keep_alive_max_probes = NULL;

    sock_domain = PyObject_GetAttrString(py_socket_options, "domain");
    if (!PyIntEnum_Check(sock_domain)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.domain is invalid");
        goto done;
    }
    socket_options->domain = (enum aws_socket_domain)PyIntEnum_AsLong(sock_domain);

    sock_type = PyObject_GetAttrString(py_socket_options, "type");
    if (!PyIntEnum_Check(sock_type)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.type is invalid");
        goto done;
    }
    socket_options->type = (enum aws_socket_type)PyIntEnum_AsLong(sock_type);

    connect_timeout_ms = PyObject_GetAttrString(py_socket_options, "connect_timeout_ms");
    if (!PyLongOrInt_Check(connect_timeout_ms)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.connect_timeout_ms is invalid");
        goto done;
    }
    socket_options->connect_timeout_ms = (uint32_t)PyLong_AsLong(connect_timeout_ms);

    keep_alive = PyObject_GetAttrString(py_socket_options, "keep_alive");
    if (!keep_alive) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive is invalid");
        goto done;
    }
    socket_options->keepalive = (bool)PyObject_IsTrue(keep_alive);

    keep_alive_interval = PyObject_GetAttrString(py_socket_options, "keep_alive_interval_secs");
    if (!PyLongOrInt_Check(keep_alive_interval)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive_interval_secs is invalid");
        goto done;
    }
    socket_options->keep_alive_interval_sec = (uint16_t)PyLong_AsLong(keep_alive_interval);

    keep_alive_timeout = PyObject_GetAttrString(py_socket_options, "keep_alive_timeout_secs");
    if (!PyLongOrInt_Check(keep_alive_timeout)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive_timeout_secs is invalid");
        goto done;
    }
    socket_options->keep_alive_timeout_sec = (uint16_t)PyLong_AsLong(keep_alive_timeout);

    keep_alive_max_probes = PyObject_GetAttrString(py_socket_options, "keep_alive_max_probes");
    if (!PyLongOrInt_Check(keep_alive_timeout)) {
        PyErr_SetString(PyExc_TypeError, "SocketOptions.keep_alive_max_probes is invalid");
        goto done;
    }
    socket_options->keep_alive_max_failed_probes = (uint16_t)PyLong_AsLong(keep_alive_max_probes);

    success = true;

done:
    Py_DECREF(sock_domain);
    Py_DECREF(sock_type);
    Py_DECREF(connect_timeout_ms);
    Py_DECREF(keep_alive);
    Py_DECREF(keep_alive_interval);
    Py_DECREF(keep_alive_timeout);
    Py_DECREF(keep_alive_max_probes);

    if (!success) {
        AWS_ZERO_STRUCT(*socket_options);
    }
    return success;
}

PyObject *aws_py_is_alpn_available(PyObject *self, PyObject *args) {

    (void)self;
    (void)args;

    return PyBool_FromLong(aws_tls_is_alpn_available());
}

/* Callback when native event-loop-group finishes its async cleanup */
static void s_elg_native_cleanup_complete(void *elg_memory) {
    aws_mem_release(aws_py_get_allocator(), elg_memory);
}

static void s_elg_capsule_destructor(PyObject *elg_capsule) {
    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
    assert(elg);

    /* Must use async cleanup.
     * We could deadlock if we ran the synchronous cleanup from an event-loop thread. */
    aws_event_loop_group_cleanup_async(elg, s_elg_native_cleanup_complete, elg);
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

    PyObject *capsule = PyCapsule_New(elg, s_capsule_name_elg, s_elg_capsule_destructor);
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

    PyObject *elg_capsule = PyObject_GetAttrString(event_loop_group, "_binding");
    if (elg_capsule) {
        native = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
        assert(native);
        Py_DECREF(elg_capsule);
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

    PyObject *binding_capsule = PyObject_GetAttrString(host_resolver, "_binding");
    if (binding_capsule) {
        struct host_resolver_binding *binding = PyCapsule_GetPointer(binding_capsule, s_capsule_name_host_resolver);
        if (binding) {
            native = &binding->native;
            assert(native);
        }
        Py_DECREF(binding_capsule);
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

    PyObject *binding_capsule = PyObject_GetAttrString(client_bootstrap, "_binding");
    if (binding_capsule) {
        struct client_bootstrap_binding *binding =
            PyCapsule_GetPointer(binding_capsule, s_capsule_name_client_bootstrap);
        if (binding) {
            native = binding->native;
            assert(native);
        }
        Py_DECREF(binding_capsule);
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

    PyObject *capsule = PyObject_GetAttrString(tls_ctx, "_binding");
    if (capsule) {
        native = PyCapsule_GetPointer(capsule, s_capsule_name_tls_ctx);
        assert(native);
        Py_DECREF(capsule);
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

    PyObject *binding_capsule = PyObject_GetAttrString(tls_connection_options, "_binding");
    if (binding_capsule) {
        struct tls_connection_options_binding *binding =
            PyCapsule_GetPointer(binding_capsule, s_capsule_name_tls_conn_options);
        if (binding) {
            native = &binding->native;
            assert(native);
        }
        Py_DECREF(binding_capsule);
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

/* aws_input_stream implementation for accessing Python I/O classes */
struct aws_input_stream_py_impl {
    struct aws_input_stream base;

    bool is_end_of_stream;

    /* Dependencies that must outlive this */
    PyObject *io;
};

static void s_aws_input_stream_py_destroy(struct aws_input_stream *stream) {
    struct aws_input_stream_py_impl *impl = stream->impl;
    Py_DECREF(impl->io);
    aws_mem_release(stream->allocator, stream);
}

static int s_aws_input_stream_py_seek(
    struct aws_input_stream *stream,
    aws_off_t offset,
    enum aws_stream_seek_basis basis) {

    struct aws_input_stream_py_impl *impl = stream->impl;

    int aws_result = AWS_OP_SUCCESS;
    PyObject *method_result = NULL;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    method_result = PyObject_CallMethod(impl->io, "seek", "(li)", &offset, &basis);
    if (!method_result) {
        aws_result = aws_py_raise_error();
        goto done;
    }

    /* Clear EOF */
    impl->is_end_of_stream = false;

done:
    Py_XDECREF(method_result);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return aws_result;
}

int s_aws_input_stream_py_read(struct aws_input_stream *stream, struct aws_byte_buf *dest) {
    struct aws_input_stream_py_impl *impl = stream->impl;

    int aws_result = AWS_OP_SUCCESS;
    PyObject *memory_view = NULL;
    PyObject *method_result = NULL;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    memory_view = aws_py_memory_view_from_byte_buffer(dest);
    if (!memory_view) {
        aws_result = aws_py_raise_error();
        goto done;
    }

    method_result = PyObject_CallMethod(impl->io, "readinto", "(O)", memory_view);
    if (!method_result) {
        aws_result = aws_py_raise_error();
        goto done;
    }

    /* Return the number of bytes read. If the object is in non-blocking mode
     * and no bytes are available, None is returned */
    Py_ssize_t bytes_read = 0;
    if (method_result != Py_None) {
        bytes_read = PyLong_AsSsize_t(method_result);
        if (bytes_read == -1 && PyErr_Occurred()) {
            aws_result = aws_py_raise_error();
            goto done;
        }
        AWS_FATAL_ASSERT(bytes_read >= 0);

        if (bytes_read == 0) {
            impl->is_end_of_stream = true;
        } else {
            dest->len += bytes_read;
        }
    }

done:
    Py_XDECREF(memory_view);
    Py_XDECREF(method_result);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return aws_result;
}

int s_aws_input_stream_py_get_status(struct aws_input_stream *stream, struct aws_stream_status *status) {
    struct aws_input_stream_py_impl *impl = stream->impl;

    status->is_valid = true;
    status->is_end_of_stream = impl->is_end_of_stream;

    return AWS_OP_SUCCESS;
}

int s_aws_input_stream_py_get_length(struct aws_input_stream *stream, int64_t *out_length) {
    (void)stream;
    (void)out_length;
    return AWS_ERROR_UNIMPLEMENTED;
}

static struct aws_input_stream_vtable s_aws_input_stream_py_vtable = {
    .seek = s_aws_input_stream_py_seek,
    .read = s_aws_input_stream_py_read,
    .get_status = s_aws_input_stream_py_get_status,
    .get_length = s_aws_input_stream_py_get_length,
    .destroy = s_aws_input_stream_py_destroy,
};

struct aws_input_stream *aws_input_stream_new_from_py(PyObject *io) {

    if (!io || (io == Py_None)) {
        aws_raise_error(AWS_ERROR_INVALID_ARGUMENT);
        return NULL;
    }

    struct aws_allocator *alloc = aws_py_get_allocator();
    struct aws_input_stream_py_impl *impl = aws_mem_calloc(alloc, 1, sizeof(struct aws_input_stream_py_impl));
    if (!impl) {
        return NULL;
    }

    impl->base.allocator = alloc;
    impl->base.vtable = &s_aws_input_stream_py_vtable;
    impl->base.impl = impl;
    impl->io = io;
    Py_INCREF(impl->io);

    return &impl->base;
}
