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

/*******************************************************************************
 * New Client
 ******************************************************************************/

static void s_mqtt_python_client_destructor(PyObject *client_capsule) {

    assert(PyCapsule_CheckExact(client_capsule));

    struct mqtt_python_client *py_client = PyCapsule_GetPointer(client_capsule, s_capsule_name_mqtt_client);
    assert(py_client);

    struct aws_allocator *allocator = py_client->native_client.allocator;

    aws_mqtt_client_clean_up(&py_client->native_client);
    aws_mem_release(allocator, py_client);
}

PyObject *aws_py_mqtt_client_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    struct mqtt_python_client *py_client = NULL;

    PyObject *bootstrap_capsule = NULL;

    if (!PyArg_ParseTuple(args, "O", &bootstrap_capsule)) {
        goto error;
    }

    if (!bootstrap_capsule || !PyCapsule_CheckExact(bootstrap_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }
    struct aws_client_bootstrap *bootstrap = PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_client_bootstrap);
    if (!bootstrap) {
        goto error;
    }

    py_client = aws_mem_acquire(allocator, sizeof(struct mqtt_python_client));
    if (!py_client) {
        PyErr_SetAwsLastError();
        goto error;
    }
    AWS_ZERO_STRUCT(*py_client);

    if (aws_mqtt_client_init(&py_client->native_client, allocator, bootstrap)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return PyCapsule_New(py_client, s_capsule_name_mqtt_client, s_mqtt_python_client_destructor);

error:
    if (py_client) {
        aws_mem_release(allocator, py_client);
    }

    return NULL;
}
