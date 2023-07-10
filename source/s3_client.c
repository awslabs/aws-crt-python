/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "s3.h"

#include "auth.h"
#include "io.h"
#include <aws/s3/s3_client.h>

static const char *s_capsule_name_s3_client = "aws_s3_client";

struct s3_client_binding {
    struct aws_s3_client *native;

    /* Shutdown callback, reference cleared after invoking callback */
    PyObject *on_shutdown;
    /* Reference to python object that reference to other related python object to keep it alive */
    PyObject *py_core;
};

static void s_destroy(struct s3_client_binding *client) {
    Py_XDECREF(client->on_shutdown);
    Py_XDECREF(client->py_core);
    aws_mem_release(aws_py_get_allocator(), client);
}

/* Invoked when the python object get cleaned up */
static void s_s3_client_capsule_destructor(PyObject *capsule) {
    struct s3_client_binding *client = PyCapsule_GetPointer(capsule, s_capsule_name_s3_client);

    if (client->native) {
        aws_s3_client_release(client->native);
    } else {
        /* we hit this branch if things failed part way through setting up the binding,
         * before the native aws_s3_meta_request could be created. */
        s_destroy(client);
    }
}

/* Callback from C land, invoked when the underlying shutdown process finished */
static void s_s3_client_shutdown(void *user_data) {
    struct s3_client_binding *client = user_data;

    /* Lock for python */
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Invoke on_shutdown, then clear our reference to it */
    PyObject *result = PyObject_CallFunction(client->on_shutdown, NULL);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    s_destroy(client);

    PyGILState_Release(state);
}

struct aws_s3_client *aws_py_get_s3_client(PyObject *client) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(client, s_capsule_name_s3_client, "S3Client", s3_client_binding);
}

PyObject *aws_py_s3_client_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py = NULL;
    PyObject *signing_config_py = NULL;
    PyObject *credential_provider_py = NULL;
    PyObject *tls_options_py = NULL;
    PyObject *on_shutdown_py = NULL;
    PyObject *py_core = NULL;
    const char *region;
    Py_ssize_t region_len;
    uint64_t part_size = 0;
    double throughput_target_gbps = 0;
    int tls_mode;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOs#iKdO",
            &bootstrap_py,
            &signing_config_py,
            &credential_provider_py,
            &tls_options_py,
            &on_shutdown_py,
            &region,
            &region_len,
            &tls_mode,
            &part_size,
            &throughput_target_gbps,
            &py_core)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct aws_credentials_provider *credential_provider = NULL;
    if (credential_provider_py != Py_None) {
        credential_provider = aws_py_get_credentials_provider(credential_provider_py);
        if (!credential_provider) {
            return NULL;
        }
    }
    struct aws_signing_config_aws *signing_config = NULL;
    if (signing_config_py != Py_None) {
        signing_config = aws_py_get_signing_config(signing_config_py);
        if (!signing_config) {
            return NULL;
        }
    }
    struct aws_signing_config_aws signing_config_from_credentials_provider;
    AWS_ZERO_STRUCT(signing_config_from_credentials_provider);

    struct aws_byte_cursor region_cursor = aws_byte_cursor_from_array((const uint8_t *)region, region_len);

    if (credential_provider) {
        aws_s3_init_default_signing_config(
            &signing_config_from_credentials_provider, region_cursor, credential_provider);
        signing_config = &signing_config_from_credentials_provider;
    }

    struct aws_tls_connection_options *tls_options = NULL;
    if (tls_options_py != Py_None) {
        tls_options = aws_py_get_tls_connection_options(tls_options_py);
        if (!tls_options) {
            return NULL;
        }
    }

    struct s3_client_binding *s3_client = aws_mem_calloc(allocator, 1, sizeof(struct s3_client_binding));
    if (!s3_client) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur */

    PyObject *capsule = PyCapsule_New(s3_client, s_capsule_name_s3_client, s_s3_client_capsule_destructor);
    if (!capsule) {
        aws_mem_release(allocator, s3_client);
        return NULL;
    }

    s3_client->on_shutdown = on_shutdown_py;
    Py_INCREF(s3_client->on_shutdown);

    s3_client->py_core = py_core;
    Py_INCREF(s3_client->py_core);

    struct aws_s3_client_config s3_config = {
        .region = aws_byte_cursor_from_array((const uint8_t *)region, region_len),
        .client_bootstrap = bootstrap,
        .tls_mode = tls_mode,
        .signing_config = signing_config,
        .part_size = part_size,
        .tls_connection_options = tls_options,
        .throughput_target_gbps = throughput_target_gbps,
        .shutdown_callback = s_s3_client_shutdown,
        .shutdown_callback_user_data = s3_client,
    };

    s3_client->native = aws_s3_client_new(allocator, &s3_config);
    if (s3_client->native == NULL) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;

error:
    Py_DECREF(capsule);
    return NULL;
}
