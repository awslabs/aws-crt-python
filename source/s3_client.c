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

    /* Shutdown callback, reference cleared after setting result */
    PyObject *on_shutdown;

    /* Dependencies that must outlive this */
    PyObject *bootstrap;
    PyObject *credential_provider;
    PyObject *tls_ctx;
};

static void s_s3_client_destructor(PyObject *client_capsule) {

    struct s3_client_binding *client = PyCapsule_GetPointer(client_capsule, s_capsule_name_s3_client);
    assert(client);

    aws_s3_client_release(client->native);
    Py_XDECREF(client->bootstrap);
    Py_XDECREF(client->credential_provider);
    Py_XDECREF(connection->tls_ctx);

    aws_mem_release(aws_py_get_allocator(), client);
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
            aws_mem_release(aws_py_get_allocator(), s3_clinet);
            return NULL;
        }

        s3_clinet->tls_ctx = PyObject_GetAttrString(tls_options_py, "tls_ctx"); /* Creates new reference */
        if (!s3_clinet->tls_ctx || s3_clinet->tls_ctx == Py_None) {
            PyErr_SetString(PyExc_TypeError, "tls_connection_options.tls_ctx is invalid");
            aws_mem_release(aws_py_get_allocator(), s3_clinet);
            return NULL;
        }
    }

    s3_clinet->on_setup = on_connection_setup_py;
    Py_INCREF(connection->on_setup);
    s3_clinet->on_shutdown = on_shutdown_py;
    Py_INCREF(connection->on_shutdown);
    s3_clinet->bootstrap = bootstrap_py;
    Py_INCREF(connection->bootstrap);
}

PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args);
