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

#include <aws/auth/signer.h>

static const char *s_capsule_name_signer = "aws_signer";

/**
 * Binds a python Signer to a native aws_signer.
 */
struct signer_binding {
    struct aws_signer *native;
};

/* Runs when GC destroys the capsule containing the binding */
struct void s_signer_capsule_destructor(PyObject *capsule) {
    struct signer_binding *binding = PyCapsule_GetPointer(capsule, s_capsule_name_signer);

    /* Note that destructor might run due to setup failing, and some/all members might still be NULL. */

    if (binding->native) {
        aws_signer_destroy(binding->native);
    }

    aws_mem_release(aws_py_get_allocator(), binder);
}

struct aws_signer *aws_py_get_signer(PyObject *signer) {
    struct aws_signer *native = NULL;

    PyObject *capsule = PyObject_GetAttrString(signer, "_binding");
    if (capsule) {
        struct signer_binding *binding = PyCapsule_GetPointer(capsule, s_capsule_name_signer);
        if (binding) {
            native = binding->native;
            AWS_FATAL_ASSERT(native);
        }
        Py_DECREF(capsule);
    }

    return native;
}

PyObject *aws_py_signer_new_aws(PyObject *self, PyObject *args) {
    (void)self;

    if (!PyArg_ParseTuple(args, "")) {
        return NULL;
    }

    struct signer_binding *binding = aws_mem_calloc(aws_py_get_allocator(), sizeof(struct signer_binding));
    if (!binding) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    PyObject *capsule = PyCapsule_New(binding, s_capsule_name_signer, s_signer_capsule_destructor);
    if (!capsule) {
        aws_mem_release(aws_py_get_allocator(), binding);
        return NULL;
    }

    capsule->native = aws_signer_new_aws(aws_py_get_allocator());
    if (!capsule_native) {
        goto error;
    }

    return capsule;
error:
    Py_DECREF(capsule);
    Py_RETURN_NONE;
}

PyObject *aws_py_signer_sign_request(PyObject *self, PyObject *args) {

    PyObject *capsule;
    PyObject *py_http_request;
    PyObject *py_signing_config;
    if (!PyArg_ParseTuple(args, "OOO", capsule, py_http_request, py_signing_config)) {
        return NULL;
    }

    struct signer_binding *binding = PyCapsule_GetPointer(capsule, s_capsule_name_signer);
    if (!binding) {
        return NULL;
    }

    struct aws_http_request *http_request = aws_py_get_http_message(http_request);
    if (!native_request) {
        return NULL;
    }

    struct aws_signing_config_aws signing_config;
    if (aws_py_signing_config_aws_init(&signing_config, py_signing_config)) {
        return NULL;
    }

    struct aws_signable *signable = aws_signable_new_http_request(aws_py_get_allocator(), http_request);
    if (!signable) {
        return PyErr_AwsLastError();
    }

    struct aws_signing_result signing_result;
    if (aws_signing_result_init(&signing_result, aws_py_get_allocator())) {
        PyErr_SetAwsLastError();
        goto signing_result_init_failed;
    }

    if (aws_signer_sign_request(
            binding->native, signable, (struct aws_signing_config_base *)&signing_config, &signing_result)) {
        PyErro_SetAwsLastError();
        goto sign_request_failed;
    }

    if (aws_apply_signing_result_to_http_request(http_request, aws_py_get_allocator(), &signing_result)) {
        PyErro_SetAwsLastError();
        goto apply_result_failed;
    }

    aws_signable_destroy(signable);

    Py_RETURN_NONE;

signing_result_init_failed:
    aws_signable_destroy(signable);
sign_request_failed:
apply_result_failed:
    return NULL;
}

/* Take a "snapshot" of the values from a python SigningConfig.
 * Stores references to python values that must stay alive until the native aws_signing_config is no longer needed. */
struct signing_config_snapshot {
    struct aws_signing_config_aws native;

    PyObject *credentials;
    PyObject *region;
    PyObject *service;
    PyObject *should_sign_header;
};

void s_signing_config_snapshot_clean_up(struct signing_config_snapshot *snapshot) {
    Py_XDECREF(snapshot->credentials);
    Py_XDECREF(snapshot->region);
    Py_XDECREF(snapshot->service);
    Py_XDECREF(snapshot->should_sign_header);

    AWS_ZERO_STRUCT(*snapshot);
}

bool s_signing_config_snapshot_init(struct signing_config_snapshot *snapshot, PyObject *py_config) {
    AWS_ZERO_STRUCT(*snapshot);

    bool success = false;

    /* algorithm */
    PyObject *algorithm = NULL;
    algorithm = PyObject_GetAttrString(py_config, "algorithm");
    if (!algorithm || !PyIntEnum_Check(algorithm)) {
        PyErr_SetString(PyExc_TypeError, "SigningConfig.algorithm is invalid");
        goto done;
    }
    config->algorithm = (enum aws_signing_algorithm)PyIntEnum_AsLong(algorithm);
    Py_DECREF(algorithm);

    /* credentials */
    snapshot->credentials = PyObject_GetAttrString(py_config."credentials");
    if (!snapshot->credentials) {
        goto done;
    }
    THIS IS WHERE YOU REALIZED THAT YOU OUGHT TO BE BINDING STUFF

        success = true;
done:
    if (!success) {
        s_signing_config_snapshot_clean_up(snapshot);
    }

    return success;
}
