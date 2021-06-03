/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "auth.h"

#include "http.h"

#include <aws/auth/signable.h>
#include <aws/auth/signing.h>
#include <aws/auth/signing_result.h>

/* Object that stays alive for duration async signing operation */
struct async_signing_data {
    PyObject *py_http_request;
    struct aws_http_message *http_request; /* owned by py_http_request, do not clean up. */
    PyObject *py_signing_config;
    PyObject *py_on_complete;
    struct aws_signable *signable;
};

static void s_async_signing_data_destroy(struct async_signing_data *async_data) {
    if (async_data) {
        Py_XDECREF(async_data->py_http_request);
        Py_XDECREF(async_data->py_signing_config);
        Py_XDECREF(async_data->py_on_complete);
        aws_signable_destroy(async_data->signable);
        aws_mem_release(aws_py_get_allocator(), async_data);
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
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

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

PyObject *aws_py_sign_request_aws(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_http_request;
    PyObject *py_signing_config;
    PyObject *py_on_complete;
    if (!PyArg_ParseTuple(args, "OOO", &py_http_request, &py_signing_config, &py_on_complete)) {
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

    async_data->py_http_request = py_http_request;
    Py_INCREF(async_data->py_http_request);

    async_data->http_request = http_request;

    async_data->py_signing_config = py_signing_config;
    Py_INCREF(async_data->py_signing_config);

    async_data->py_on_complete = py_on_complete;
    Py_INCREF(async_data->py_on_complete);

    async_data->signable = aws_signable_new_http_request(aws_py_get_allocator(), http_request);
    if (!async_data->signable) {
        PyErr_SetAwsLastError();
        goto error;
    }

    if (aws_sign_request_aws(
            alloc,
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
