/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "io.h"

#include <aws/common/atomics.h>

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
static const char *s_capsule_name_input_stream = "aws_input_stream";

bool aws_py_socket_options_init(struct aws_socket_options *socket_options, PyObject *py_socket_options) {
    AWS_ZERO_STRUCT(*socket_options);

    bool success = false;

    socket_options->domain = PyObject_GetAttrAsIntEnum(py_socket_options, "SocketOptions", "domain");
    if (PyErr_Occurred()) {
        goto done;
    }

    socket_options->type = PyObject_GetAttrAsIntEnum(py_socket_options, "SocketOptions", "type");
    if (PyErr_Occurred()) {
        goto done;
    }

    socket_options->connect_timeout_ms =
        PyObject_GetAttrAsUint32(py_socket_options, "SocketOptions", "connect_timeout_ms");
    if (PyErr_Occurred()) {
        goto done;
    }

    socket_options->keepalive = PyObject_GetAttrAsBool(py_socket_options, "SocketOptions", "keep_alive");
    if (PyErr_Occurred()) {
        goto done;
    }

    socket_options->keep_alive_interval_sec =
        PyObject_GetAttrAsUint16(py_socket_options, "SocketOptions", "keep_alive_interval_secs");
    if (PyErr_Occurred()) {
        goto done;
    }

    socket_options->keep_alive_timeout_sec =
        PyObject_GetAttrAsUint16(py_socket_options, "SocketOptions", "keep_alive_timeout_secs");
    if (PyErr_Occurred()) {
        goto done;
    }

    socket_options->keep_alive_max_failed_probes =
        PyObject_GetAttrAsUint16(py_socket_options, "SocketOptions", "keep_alive_max_probes");
    if (PyErr_Occurred()) {
        goto done;
    }

    success = true;

done:
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

PyObject *aws_py_is_tls_cipher_supported(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    int cipher_pref = 0;

    if (!PyArg_ParseTuple(args, "i", &cipher_pref)) {
        return NULL;
    }

    return PyBool_FromLong(aws_tls_is_cipher_pref_supported(cipher_pref));
}
/*******************************************************************************
 * AWS_EVENT_LOOP_GROUP
 ******************************************************************************/

struct event_loop_group_binding {
    struct aws_event_loop_group *native;

    /* Dependencies that must outlive this */
    PyObject *shutdown_complete;
};

/* Callback when native event-loop-group finishes its async cleanup */
static void s_elg_native_cleanup_complete(void *user_data) {
    struct event_loop_group_binding *elg_binding = user_data;
    PyObject *shutdown_complete = elg_binding->shutdown_complete;

    aws_mem_release(aws_py_get_allocator(), elg_binding);

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallFunction(shutdown_complete, "()");
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_DECREF(shutdown_complete);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

static void s_elg_capsule_destructor(PyObject *elg_capsule) {
    struct event_loop_group_binding *elg_binding = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);

    /* Must use async cleanup.
     * We could deadlock if we ran the synchronous cleanup from an event-loop thread. */
    aws_event_loop_group_release(elg_binding->native);
}

PyObject *aws_py_event_loop_group_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    uint16_t num_threads;
    int is_pinned;
    uint16_t cpu_group;
    PyObject *shutdown_complete_py;
    if (!PyArg_ParseTuple(args, "HpHO", &num_threads, &is_pinned, &cpu_group, &shutdown_complete_py)) {
        return NULL;
    }

    struct event_loop_group_binding *binding = aws_mem_calloc(allocator, 1, sizeof(struct event_loop_group_binding));
    if (!binding) {
        return PyErr_AwsLastError();
    }

    struct aws_shutdown_callback_options shutdown_options = {
        .shutdown_callback_fn = s_elg_native_cleanup_complete,
        .shutdown_callback_user_data = binding,
    };

    if (is_pinned) {
        binding->native =
            aws_event_loop_group_new_default_pinned_to_cpu_group(allocator, num_threads, cpu_group, &shutdown_options);
    } else {
        binding->native = aws_event_loop_group_new_default(allocator, num_threads, &shutdown_options);
    }
    if (binding->native == NULL) {
        PyErr_SetAwsLastError();
        goto elg_init_failed;
    }

    PyObject *capsule = PyCapsule_New(binding, s_capsule_name_elg, s_elg_capsule_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    AWS_FATAL_ASSERT(shutdown_complete_py != Py_None);
    binding->shutdown_complete = shutdown_complete_py;
    Py_INCREF(binding->shutdown_complete);

    return capsule;

capsule_new_failed:
    aws_event_loop_group_release(binding->native);
elg_init_failed:
    aws_mem_release(allocator, binding);
    return NULL;
}

struct aws_event_loop_group *aws_py_get_event_loop_group(PyObject *event_loop_group) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(event_loop_group, s_capsule_name_elg, "EventLoopGroup", event_loop_group_binding);
}

/*******************************************************************************
 * AWS_HOST_RESOLVER
 ******************************************************************************/

struct host_resolver_binding {
    struct aws_host_resolver *native;

    /* Dependencies that must outlive this */
    PyObject *event_loop_group;
};

static void s_host_resolver_destructor(PyObject *host_resolver_capsule) {
    struct host_resolver_binding *host_resolver =
        PyCapsule_GetPointer(host_resolver_capsule, s_capsule_name_host_resolver);
    assert(host_resolver);
    aws_host_resolver_release(host_resolver->native);
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
    struct aws_host_resolver_default_options resolver_options = {
        .max_entries = max_hosts,
        .el_group = elg,
    };

    host_resolver->native = aws_host_resolver_new_default(allocator, &resolver_options);
    if (host_resolver->native == NULL) {
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
    aws_host_resolver_release(host_resolver->native);
resolver_init_failed:
    aws_mem_release(allocator, host_resolver);
    return NULL;
}

struct aws_host_resolver *aws_py_get_host_resolver(PyObject *host_resolver) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        host_resolver, s_capsule_name_host_resolver, "HostResolverBase", host_resolver_binding);
}

struct client_bootstrap_binding {
    struct aws_client_bootstrap *native;

    /* Dependencies that must outlive this */
    PyObject *event_loop_group;
    PyObject *host_resolver;
    PyObject *shutdown_complete;
};

/* Fires after the native client bootstrap finishes shutting down. */
static void s_client_bootstrap_on_shutdown_complete(void *user_data) {
    struct client_bootstrap_binding *bootstrap = user_data;
    PyObject *shutdown_complete = bootstrap->shutdown_complete;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    Py_XDECREF(bootstrap->host_resolver);
    Py_XDECREF(bootstrap->event_loop_group);

    aws_mem_release(aws_py_get_allocator(), bootstrap);

    if (shutdown_complete) {
        PyObject *result = PyObject_CallFunction(shutdown_complete, "()");
        if (result) {
            Py_DECREF(result);
        } else {
            PyErr_WriteUnraisable(PyErr_Occurred());
        }
        Py_DECREF(shutdown_complete);
    }

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

/* Fires when python capsule is GC'd.
 * Note that bootstrap shutdown is async, we can't release dependencies until it completes */
static void s_client_bootstrap_capsule_destructor(PyObject *bootstrap_capsule) {
    struct client_bootstrap_binding *bootstrap =
        PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_client_bootstrap);

    aws_client_bootstrap_release(bootstrap->native);
}

PyObject *aws_py_client_bootstrap_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *elg_py;
    PyObject *host_resolver_py;
    PyObject *shutdown_complete_py;

    if (!PyArg_ParseTuple(args, "OOO", &elg_py, &host_resolver_py, &shutdown_complete_py)) {
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

    PyObject *capsule =
        PyCapsule_New(bootstrap, s_capsule_name_client_bootstrap, s_client_bootstrap_capsule_destructor);
    if (!capsule) {
        goto error;
    }

    struct aws_client_bootstrap_options bootstrap_options = {
        .event_loop_group = elg,
        .host_resolver = host_resolver,
        .on_shutdown_complete = s_client_bootstrap_on_shutdown_complete,
        .user_data = bootstrap,
    };
    bootstrap->native = aws_client_bootstrap_new(allocator, &bootstrap_options);
    if (!bootstrap->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    /* From hereon, nothing will fail */

    bootstrap->event_loop_group = elg_py;
    Py_INCREF(elg_py);

    bootstrap->host_resolver = host_resolver_py;
    Py_INCREF(host_resolver_py);

    bootstrap->shutdown_complete = shutdown_complete_py;
    Py_INCREF(bootstrap->shutdown_complete);

    return capsule;

error:
    if (capsule) {
        Py_DECREF(capsule);
    } else {
        aws_mem_release(allocator, bootstrap);
    }
    return NULL;
}

struct aws_client_bootstrap *aws_py_get_client_bootstrap(PyObject *client_bootstrap) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        client_bootstrap, s_capsule_name_client_bootstrap, "ClientBootstrap", client_bootstrap_binding);
}

static void s_tls_ctx_destructor(PyObject *tls_ctx_capsule) {

    struct aws_tls_ctx *tls_ctx = PyCapsule_GetPointer(tls_ctx_capsule, s_capsule_name_tls_ctx);
    assert(tls_ctx);

    aws_tls_ctx_release(tls_ctx);
}

PyObject *aws_py_client_tls_ctx_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    int min_tls_version = 0;
    int cipher_pref = 0;
    const char *ca_dirpath;
    const char *ca_buffer;
    Py_ssize_t ca_buffer_len;
    const char *alpn_list;
    const char *certificate_buffer;
    Py_ssize_t certificate_buffer_len;
    const char *private_key_buffer;
    Py_ssize_t private_key_buffer_len;
    const char *pkcs12_filepath;
    const char *pkcs12_password;
    int verify_peer; /* p - boolean predicate */
    PyObject *py_pkcs11_lib;
    const char *pkcs11_user_pin;
    Py_ssize_t pkcs11_user_pin_len;
    PyObject *py_pkcs11_slot_id;
    const char *pkcs11_token_label;
    Py_ssize_t pkcs11_token_label_len;
    const char *pkcs11_priv_key_label;
    Py_ssize_t pkcs11_priv_key_label_len;
    const char *pkcs11_cert_file_path;
    Py_ssize_t pkcs11_cert_file_path_len;
    const char *pkcs11_cert_file_contents;
    Py_ssize_t pkcs11_cert_file_contents_len;
    const char *windows_cert_store_path;

    if (!PyArg_ParseTuple(
            args,
            "iizz#zz#z#zzpOz#Oz#z#z#z#z",
            /* i */ &min_tls_version,
            /* i */ &cipher_pref,
            /* z */ &ca_dirpath,
            /* z */ &ca_buffer,
            /* # */ &ca_buffer_len,
            /* z */ &alpn_list,
            /* z */ &certificate_buffer,
            /* # */ &certificate_buffer_len,
            /* z */ &private_key_buffer,
            /* # */ &private_key_buffer_len,
            /* z */ &pkcs12_filepath,
            /* z */ &pkcs12_password,
            /* p */ &verify_peer,
            /* O */ &py_pkcs11_lib,
            /* z */ &pkcs11_user_pin,
            /* # */ &pkcs11_user_pin_len,
            /* O */ &py_pkcs11_slot_id,
            /* z */ &pkcs11_token_label,
            /* # */ &pkcs11_token_label_len,
            /* z */ &pkcs11_priv_key_label,
            /* # */ &pkcs11_priv_key_label_len,
            /* z */ &pkcs11_cert_file_path,
            /* # */ &pkcs11_cert_file_path_len,
            /* z */ &pkcs11_cert_file_contents,
            /* # */ &pkcs11_cert_file_contents_len,
            /* z */ &windows_cert_store_path)) {
        return NULL;
    }

    struct aws_tls_ctx_options ctx_options;
    AWS_ZERO_STRUCT(ctx_options);
    if (certificate_buffer != NULL) {
        /* mTLS with certificate and private key*/
        struct aws_byte_cursor cert = aws_byte_cursor_from_array(certificate_buffer, certificate_buffer_len);
        struct aws_byte_cursor key = aws_byte_cursor_from_array(private_key_buffer, private_key_buffer_len);
        if (aws_tls_ctx_options_init_client_mtls(&ctx_options, allocator, &cert, &key)) {
            PyErr_SetAwsLastError();
            return NULL;
        }
    } else if (py_pkcs11_lib != Py_None) {
        /* mTLS with PKCS#11 */
        struct aws_pkcs11_lib *pkcs11_lib = aws_py_get_pkcs11_lib(py_pkcs11_lib);
        if (pkcs11_lib == NULL) {
            return NULL;
        }

        bool has_slot_id = false;
        uint64_t slot_id_value = 0;
        if (py_pkcs11_slot_id != Py_None) {
            has_slot_id = true;
            slot_id_value = PyLong_AsUnsignedLongLong(py_pkcs11_slot_id);
            if ((slot_id_value == (uint64_t)-1) && PyErr_Occurred()) {
                PyErr_SetString(PyExc_ValueError, "PKCS#11 slot_id is not a valid int");
                return NULL;
            }
        }

        struct aws_tls_ctx_pkcs11_options pkcs11_options = {
            .pkcs11_lib = pkcs11_lib,
            .user_pin = aws_byte_cursor_from_array(pkcs11_user_pin, pkcs11_user_pin_len),
            .slot_id = has_slot_id ? &slot_id_value : NULL,
            .token_label = aws_byte_cursor_from_array(pkcs11_token_label, pkcs11_token_label_len),
            .private_key_object_label = aws_byte_cursor_from_array(pkcs11_priv_key_label, pkcs11_priv_key_label_len),
            .cert_file_path = aws_byte_cursor_from_array(pkcs11_cert_file_path, pkcs11_cert_file_path_len),
            .cert_file_contents = aws_byte_cursor_from_array(pkcs11_cert_file_contents, pkcs11_cert_file_contents_len),
        };

        if (aws_tls_ctx_options_init_client_mtls_with_pkcs11(&ctx_options, allocator, &pkcs11_options)) {
            return PyErr_AwsLastError();
        }
    } else if (pkcs12_filepath != NULL) {
        /* mTLS with PKCS#12 */
        struct aws_byte_cursor password = aws_byte_cursor_from_c_str(pkcs12_password);
        if (aws_tls_ctx_options_init_client_mtls_pkcs12_from_path(
                &ctx_options, allocator, pkcs12_filepath, &password)) {
            return PyErr_AwsLastError();
        }
    } else if (windows_cert_store_path != NULL) {
        /* mTLS with certificate from a Windows certificate store */
        if (aws_tls_ctx_options_init_client_mtls_from_system_path(&ctx_options, allocator, windows_cert_store_path)) {
            return PyErr_AwsLastError();
        }
    } else {
        /* no mTLS */
        aws_tls_ctx_options_init_default_client(&ctx_options, allocator);
    }

    /* From hereon, we need to clean up if errors occur */

    ctx_options.minimum_tls_version = min_tls_version;
    ctx_options.cipher_pref = cipher_pref;

    if (ca_dirpath != NULL) {
        if (aws_tls_ctx_options_override_default_trust_store_from_path(&ctx_options, ca_dirpath, NULL)) {
            PyErr_SetAwsLastError();
            goto ctx_options_failure;
        }
    }

    if (ca_buffer != NULL) {
        struct aws_byte_cursor ca = aws_byte_cursor_from_array(ca_buffer, ca_buffer_len);

        if (aws_tls_ctx_options_override_default_trust_store(&ctx_options, &ca)) {
            PyErr_SetAwsLastError();
            goto ctx_options_failure;
        }
    }

    if (alpn_list != NULL) {
        if (aws_tls_ctx_options_set_alpn_list(&ctx_options, alpn_list)) {
            PyErr_SetAwsLastError();
            goto ctx_options_failure;
        }
    }

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
    aws_tls_ctx_release(tls_ctx);

ctx_options_failure:
    aws_tls_ctx_options_clean_up(&ctx_options);
    return NULL;
}

struct aws_tls_ctx *aws_py_get_tls_ctx(PyObject *tls_ctx) {
    return aws_py_get_binding(tls_ctx, s_capsule_name_tls_ctx, "TlsContextBase");
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
    AWS_PY_RETURN_NATIVE_REF_FROM_BINDING(
        tls_connection_options,
        s_capsule_name_tls_conn_options,
        "TlsConnectionOptions",
        tls_connection_options_binding);
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
    struct aws_allocator *allocator;

    bool is_end_of_stream;

    /* Track the refcount from C land */
    struct aws_atomic_var c_ref;

    /* Pointer to python self. The stream will have a same lifetime as the python Object */
    PyObject *py_self;
};

static int s_aws_input_stream_py_seek(
    struct aws_input_stream *stream,
    int64_t offset,
    enum aws_stream_seek_basis basis) {

    struct aws_input_stream_py_impl *impl = AWS_CONTAINER_OF(stream, struct aws_input_stream_py_impl, base);

    int aws_result = AWS_OP_SUCCESS;
    PyObject *method_result = NULL;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    method_result = PyObject_CallMethod(impl->py_self, "_seek", "(Li)", offset, basis);
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
    struct aws_input_stream_py_impl *impl = AWS_CONTAINER_OF(stream, struct aws_input_stream_py_impl, base);

    int aws_result = AWS_OP_SUCCESS;
    PyObject *memory_view = NULL;
    PyObject *method_result = NULL;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    memory_view = aws_py_memory_view_from_byte_buffer(dest);
    if (!memory_view) {
        aws_result = aws_py_raise_error();
        goto done;
    }

    method_result = PyObject_CallMethod(impl->py_self, "_read_into_memoryview", "(O)", memory_view);
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
    struct aws_input_stream_py_impl *impl = AWS_CONTAINER_OF(stream, struct aws_input_stream_py_impl, base);

    status->is_valid = true;
    status->is_end_of_stream = impl->is_end_of_stream;

    return AWS_OP_SUCCESS;
}

int s_aws_input_stream_py_get_length(struct aws_input_stream *stream, int64_t *out_length) {
    (void)stream;
    (void)out_length;
    return aws_raise_error(AWS_ERROR_UNIMPLEMENTED);
}

void s_aws_input_stream_py_acquire(struct aws_input_stream *stream) {
    struct aws_input_stream_py_impl *impl = AWS_CONTAINER_OF(stream, struct aws_input_stream_py_impl, base);
    size_t pre_ref = aws_atomic_fetch_add(&impl->c_ref, 1);
    if (pre_ref == 0) {
        /* Only acquire the python ref when it's a new C ref */
        /*************** GIL ACQUIRE ***************/
        PyGILState_STATE state;
        if (aws_py_gilstate_ensure(&state)) {
            return; /* Python has shut down. Nothing matters anymore, but don't crash */
        }
        Py_INCREF(impl->py_self);
        PyGILState_Release(state);
        /*************** GIL RELEASE ***************/
    }
}

void s_aws_input_stream_py_release(struct aws_input_stream *stream) {
    struct aws_input_stream_py_impl *impl = AWS_CONTAINER_OF(stream, struct aws_input_stream_py_impl, base);
    size_t pre_ref = aws_atomic_fetch_sub(&impl->c_ref, 1);
    if (pre_ref == 1) {
        /* Only release the python ref when all the C refs gone */
        /*************** GIL ACQUIRE ***************/
        PyGILState_STATE state;
        if (aws_py_gilstate_ensure(&state)) {
            return; /* Python has shut down. Nothing matters anymore, but don't crash */
        }
        Py_DECREF(impl->py_self);
        PyGILState_Release(state);
        /*************** GIL RELEASE ***************/
    }
}

static struct aws_input_stream_vtable s_aws_input_stream_py_vtable = {
    .seek = s_aws_input_stream_py_seek,
    .read = s_aws_input_stream_py_read,
    .get_status = s_aws_input_stream_py_get_status,
    .get_length = s_aws_input_stream_py_get_length,
    .acquire = s_aws_input_stream_py_acquire,
    .release = s_aws_input_stream_py_release,
};

/**
 * Begin aws_input_stream <--> InputStream binding code.
 * This is distinct from the aws_input_stream_from_pyobject() code because
 * we might someday have an InputStream in python that is wrapping an
 * aws_input_stream that was not initially created from python, and is not
 * backed by a python I/O object.
 */

static void s_input_stream_capsule_destructor(PyObject *py_capsule) {
    struct aws_input_stream *stream = PyCapsule_GetPointer(py_capsule, s_capsule_name_input_stream);
    struct aws_input_stream_py_impl *impl = AWS_CONTAINER_OF(stream, struct aws_input_stream_py_impl, base);
    aws_mem_release(impl->allocator, impl);
}

PyObject *aws_py_input_stream_new(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_self;
    if (!PyArg_ParseTuple(args, "O", &py_self)) {
        return NULL;
    }

    if (py_self == Py_None) {
        PyErr_SetString(PyExc_TypeError, "InputStream cannot be None");
        return NULL;
    }

    struct aws_allocator *alloc = aws_py_get_allocator();
    struct aws_input_stream_py_impl *impl = aws_mem_calloc(alloc, 1, sizeof(struct aws_input_stream_py_impl));
    impl->allocator = alloc;
    impl->base.vtable = &s_aws_input_stream_py_vtable;
    impl->py_self = py_self;
    aws_atomic_init_int(&impl->c_ref, 0);
    /* Lifetime of the impl will be the same as py_capsule and being handled by python */
    PyObject *py_capsule = PyCapsule_New(&impl->base, s_capsule_name_input_stream, s_input_stream_capsule_destructor);

    if (!py_capsule) {
        aws_mem_release(impl->allocator, impl);
    }

    return py_capsule;
}

struct aws_input_stream *aws_py_get_input_stream(PyObject *input_stream) {
    return aws_py_get_binding(input_stream, s_capsule_name_input_stream, "InputStream");
}
