/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "mqtt_client.h"

#include "io.h"

static const char *s_capsule_name_mqtt_client = "aws_mqtt_client";

struct mqtt_client_binding {
    struct aws_mqtt_client *native;

    /* Dependencies that must outlive this */
    PyObject *bootstrap;
    PyObject *tls_ctx;
};

static void s_mqtt_python_client_destructor(PyObject *client_capsule) {

    struct mqtt_client_binding *client = PyCapsule_GetPointer(client_capsule, s_capsule_name_mqtt_client);
    assert(client);

    aws_mqtt_client_release(client->native);
    Py_DECREF(client->bootstrap);
    Py_DECREF(client->tls_ctx);
    aws_mem_release(aws_py_get_allocator(), client);
}

PyObject *aws_py_mqtt_client_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py;
    PyObject *tls_ctx_py;
    if (!PyArg_ParseTuple(args, "OO", &bootstrap_py, &tls_ctx_py)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct mqtt_client_binding *client = aws_mem_calloc(allocator, 1, sizeof(struct mqtt_client_binding));
    if (!client) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */
    client->native = aws_mqtt_client_new(allocator, bootstrap);
    if (client->native == NULL) {
        PyErr_SetAwsLastError();
        goto client_init_failed;
    }

    PyObject *capsule = PyCapsule_New(client, s_capsule_name_mqtt_client, s_mqtt_python_client_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    /* From hereon, nothing will fail */

    client->bootstrap = bootstrap_py;
    Py_INCREF(client->bootstrap);
    client->tls_ctx = tls_ctx_py;
    Py_INCREF(client->tls_ctx);
    return capsule;

capsule_new_failed:
    aws_mqtt_client_release(client->native);
client_init_failed:
    aws_mem_release(allocator, client);
    return NULL;
}

struct aws_mqtt_client *aws_py_get_mqtt_client(PyObject *mqtt_client) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(mqtt_client, s_capsule_name_mqtt_client, "Client", mqtt_client_binding);
}
