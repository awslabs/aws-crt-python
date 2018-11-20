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

PyObject *aws_py_is_alpn_available(PyObject *self, PyObject *args) {

    (void)self;
    (void)args;

    return PyBool_FromLong(aws_tls_is_alpn_available());
}

static void s_elg_destructor(PyObject *elg_capsule) {

    assert(PyCapsule_CheckExact(elg_capsule));

    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
    assert(elg);

    aws_event_loop_group_clean_up(elg);
    aws_mem_release(elg->allocator, elg);
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

static void s_client_bootstrap_destructor(PyObject *bootstrap_capsule) {

    assert(PyCapsule_CheckExact(bootstrap_capsule));

    struct aws_client_bootstrap *bootstrap = PyCapsule_GetPointer(bootstrap_capsule, s_capsule_name_client_bootstrap);
    assert(bootstrap);

    aws_client_bootstrap_clean_up(bootstrap);
    aws_mem_release(bootstrap->allocator, bootstrap);
}

PyObject *aws_py_io_client_bootstrap_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_crt_python_get_allocator();

    PyObject *elg_capsule = NULL;

    if (!PyArg_ParseTuple(args, "O", &elg_capsule)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_mem_acquire(allocator, sizeof(struct aws_client_bootstrap));
    if (!bootstrap) {
        return PyErr_AwsLastError();
    }

    if (!elg_capsule || !PyCapsule_CheckExact(elg_capsule)) {
        PyErr_SetNone(PyExc_ValueError);
        goto error;
    }
    struct aws_event_loop_group *elg = PyCapsule_GetPointer(elg_capsule, s_capsule_name_elg);
    if (!elg) {
        goto error;
    }

    if (aws_client_bootstrap_init(bootstrap, allocator, elg, NULL, NULL)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return PyCapsule_New(bootstrap, s_capsule_name_client_bootstrap, s_client_bootstrap_destructor);

error:
    if (bootstrap) {
        aws_mem_release(allocator, bootstrap);
    }

    return NULL;
}
