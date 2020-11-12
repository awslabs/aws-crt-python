/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "s3_client.h"

#include "auth.h"
#include "io.h"

static const char *s_capsule_name_s3_client = "aws_s3_client";

struct s3_client_binding {
    struct aws_s3_client *native;

    bool release_called;
    bool shutdown_called;

    /* Shutdown callback, reference cleared after setting result */
    PyObject *on_shutdown;
};

static void s_s3_client_destroy(struct s3_client_binding *client) {
    aws_mem_release(aws_py_get_allocator(), client);
}

static void s_s3_client_release(struct s3_client_binding *client) {
    AWS_FATAL_ASSERT(!client->release_called);
    client->release_called = true;

    bool destroy_after_release = client->shutdown_called;

    aws_s3_client_release(client->native);

    if (destroy_after_release) {
        s_s3_client_destroy(client);
    }
}

/* invoked when the python object get cleaned up */
static void s_s3_client_capsule_destructor(PyObject *capsule) {
    struct s3_client_binding *client = PyCapsule_GetPointer(capsule, s_capsule_name_s3_client);
    s_s3_client_release(client);
}

/* Callback from C land, invoked when the underlying shutdown process finished */
static void s_s3_client_shutdown(void *user_data) {
    struct s3_client_binding *client = user_data;

    /* Lock for python */
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    client->shutdown_called = true;

    bool destroy_after_shutdown = client->release_called;

    /* Invoke on_shutdown, then clear our reference to it */
    PyObject *result = PyObject_CallFunction(client->on_shutdown, NULL);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_CLEAR(client->on_shutdown);

    if (destroy_after_shutdown) {
        s_s3_client_destroy(client);
    }

    PyGILState_Release(state);
}

PyObject *aws_py_s3_client_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py;
    PyObject *credential_provider_py;
    PyObject *tls_options_py;
    PyObject *on_shutdown_py;
    const char *region;
    Py_ssize_t region_len;
    uint64_t part_size;
    uint32_t connection_timeout_ms;
    double throughput_target_gbps;
    double throughput_per_vip_gbps;
    uint32_t num_connections_per_vip;
    if (!PyArg_ParseTuple(
            args,
            "OOOOs#KIddI",
            &bootstrap_py,
            &credential_provider_py,
            &tls_options_py,
            &on_shutdown_py,
            &region,
            &region_len,
            &part_size,
            &connection_timeout_ms,
            &throughput_target_gbps,
            &throughput_per_vip_gbps,
            &num_connections_per_vip)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct aws_credentials_provider *credential_provider = aws_py_get_credentials_provider(credential_provider_py);
    if (!credential_provider) {
        return NULL;
    }

    struct s3_client_binding *s3_clinet = aws_mem_calloc(allocator, 1, sizeof(struct s3_client_binding));
    if (!s3_clinet) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur */
    struct aws_tls_connection_options *tls_options = NULL;
    if (tls_options_py != Py_None) {
        tls_options = aws_py_get_tls_connection_options(tls_options_py);
        if (!tls_options) {
            goto client_init_failed;
        }
    }

    struct aws_s3_client_config s3_config = {
        .region = aws_byte_cursor_from_array((const uint8_t *)region, region_len),
        .client_bootstrap = bootstrap,
        .credentials_provider = credential_provider,
        .part_size = part_size,
        .tls_connection_options = tls_options,
        .connection_timeout_ms = connection_timeout_ms,
        .throughput_target_gbps = throughput_target_gbps,
        .throughput_per_vip_gbps = throughput_per_vip_gbps,
        .num_connections_per_vip = num_connections_per_vip,
        .shutdown_callback = s_s3_client_shutdown,
        .shutdown_callback_user_data = s3_clinet,
    };

    s3_clinet->native = aws_s3_client_new(allocator, &s3_config);
    if (s3_clinet->native == NULL) {
        PyErr_SetAwsLastError();
        goto client_init_failed;
    }

    PyObject *capsule = PyCapsule_New(s3_clinet, s_capsule_name_s3_client, s_s3_client_capsule_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    s3_clinet->on_shutdown = on_shutdown_py;
    Py_INCREF(s3_clinet->on_shutdown);

    return capsule;

capsule_new_failed:
    aws_s3_client_release(s3_clinet->native);
client_init_failed:
    aws_mem_release(allocator, s3_clinet);
    return NULL;
}

// PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args);
