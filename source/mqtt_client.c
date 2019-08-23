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
#include "mqtt_client.h"

#include "io.h"

const char *s_capsule_name_mqtt_client = "aws_mqtt_client";

struct mqtt_client_binding {
    struct aws_mqtt_client native;

    /* Dependencies that must outlive us */
    PyObject *bootstrap;
    PyObject *tls_ctx;
};

static void s_mqtt_python_client_destructor(PyObject *client_capsule) {

    struct mqtt_client_binding *client = PyCapsule_GetPointer(client_capsule, s_capsule_name_mqtt_client);
    assert(client);

    aws_mqtt_client_clean_up(&client->native);
    Py_DECREF(client->bootstrap);
    Py_DECREF(client->tls_ctx);
    aws_mem_release(aws_crt_python_get_allocator(), client);
}

PyObject *aws_py_mqtt_client_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    PyObject *bootstrap_py;
    PyObject *tls_ctx_py;
    if (!PyArg_ParseTuple(args, "OO", &bootstrap_py, &tls_ctx_py)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = get_aws_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct mqtt_client_binding *client = aws_mem_calloc(allocator, 1, sizeof(struct mqtt_client_binding));
    if (!client) {
        PyErr_SetAwsLastError();
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur */

    PyObject *capsule = PyCapsule_New(client, s_capsule_name_mqtt_client, s_mqtt_python_client_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    if (aws_mqtt_client_init(&client->native, allocator, bootstrap)) {
        PyErr_SetAwsLastError();
        goto client_init_failed;
    }

    /* From hereon, nothing will fail */

    client->bootstrap = bootstrap_py;
    Py_INCREF(client->bootstrap);
    client->tls_ctx = tls_ctx_py;
    Py_INCREF(client->tls_ctx);
    return capsule;

client_init_failed:
    Py_DECREF(capsule);
capsule_new_failed:
    aws_mem_release(allocator, client);
    return NULL;
}

struct aws_mqtt_client *get_aws_mqtt_client(PyObject *mqtt_client) {
    struct aws_mqtt_client *native = NULL;

    PyObject *binding_capsule = PyObject_GetAttrString(mqtt_client, "_binding");
    if (binding_capsule) {
        struct mqtt_client_binding *binding = PyCapsule_GetPointer(binding_capsule, s_capsule_name_mqtt_client);
        if (binding) {
            native = &binding->native;
            assert(native);
        }
        Py_DECREF(binding_capsule);
    }

    return native;
}
