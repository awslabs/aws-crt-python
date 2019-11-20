/*
 * Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

#include "auth.h"

#include "http.h"

#include <aws/auth/signable.h>
#include <aws/auth/signer.h>

static const char *s_capsule_name_signer = "aws_signer";

/* Signer capsule contains raw aws_signer struct. There is no intermediate binding struct. */

/* Runs when GC destroys the capsule containing the binding */
static void s_signer_capsule_destructor(PyObject *py_capsule) {
    struct aws_signer *signer = PyCapsule_GetPointer(py_capsule, s_capsule_name_signer);
    aws_signer_destroy(signer);
}

struct aws_signer *aws_py_get_signer(PyObject *py_signer) {
    return aws_py_get_binding(py_signer, s_capsule_name_signer, "AwsSigner");
}

PyObject *aws_py_signer_new_aws(PyObject *self, PyObject *args) {
    (void)self;

    if (!PyArg_ParseTuple(args, "")) {
        return NULL;
    }

    struct aws_signer *signer = aws_signer_new_aws(aws_py_get_allocator());
    if (!signer) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur. */

    PyObject *py_capsule = PyCapsule_New(signer, s_capsule_name_signer, s_signer_capsule_destructor);
    if (!py_capsule) {
        aws_signer_destroy(signer);
        return NULL;
    }

    return py_capsule;
}

/* Object that stays alive for duration async signing operation */
struct async_signing_data {
    PyObject *py_signer;
    PyObject *py_http_request;
    struct aws_http_message *http_request; /* owned by py_http_request, do not clean up. */
    PyObject *py_signing_config;
    PyObject *py_on_complete;
    struct aws_signable *signable;
};

static void s_async_signing_data_destroy(struct async_signing_data *async_data) {
    if (async_data) {
        Py_XDECREF(async_data->py_signer);
        Py_XDECREF(async_data->py_http_request);
        Py_XDECREF(async_data->py_signing_config);
        Py_XDECREF(async_data->py_on_complete);
        aws_signable_destroy(async_data->signable);
    }
}

static void s_signing_complete(struct aws_signing_result *signing_result, int error_code, void *userdata) {
    struct async_signing_data *async_data = userdata;

    if (!error_code) {
        struct aws_allocator *allocator = aws_py_get_allocator();

        if (aws_apply_signing_result_to_http_request(async_data->http_request, allocator, signing_result)) {
            error_code = aws_last_error();
        }
    }

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *py_result = PyObject_CallFunction(async_data->py_on_complete, "(i)", error_code);
    if (py_result) {
        Py_DECREF(py_result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    s_async_signing_data_destroy(async_data);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

PyObject *aws_py_signer_sign_request(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_signer;
    PyObject *py_http_request;
    PyObject *py_signing_config;
    PyObject *py_on_complete;
    if (!PyArg_ParseTuple(args, "OOOO", &py_signer, &py_http_request, &py_signing_config, &py_on_complete)) {
        return NULL;
    }

    struct aws_signer *signer = aws_py_get_signer(py_signer);
    if (!signer) {
        return NULL;
    }

    struct aws_http_message *http_request = aws_py_get_http_message(py_http_request);
    if (!http_request) {
        return NULL;
    }

    struct aws_signing_config_aws *signing_config = aws_py_get_signing_config(py_signing_config);
    if (!signing_config) {
        return NULL;
    }

    AWS_FATAL_ASSERT(py_on_complete != Py_None);

    struct aws_allocator *alloc = aws_py_get_allocator();

    struct async_signing_data *async_data = aws_mem_calloc(alloc, 1, sizeof(struct async_signing_data));
    if (!async_data) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if anything goes wrong.
     * Fortunately async_data's destroy fn will clean up anything stored inside of it. */

    async_data->py_signer = py_signer;
    Py_INCREF(async_data->py_signer);

    async_data->py_http_request = py_http_request;
    Py_INCREF(async_data->py_http_request);

    async_data->http_request = http_request;

    async_data->py_signing_config = py_signing_config;
    Py_INCREF(async_data->py_signing_config);

    async_data->py_on_complete = py_on_complete;
    Py_INCREF(async_data->py_on_complete);

    async_data->signable = aws_signable_new_http_request(aws_py_get_allocator(), http_request);
    if (!async_data->signable) {
        goto error;
    }

    if (aws_signer_sign_request(
            signer,
            async_data->signable,
            (struct aws_signing_config_base *)signing_config,
            s_signing_complete,
            async_data)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    Py_RETURN_NONE;

error:
    s_async_signing_data_destroy(async_data);
    return NULL;
}
