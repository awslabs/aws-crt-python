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

#include <aws/auth/signing_config.h>

static const char *s_capsule_name_signing_config = "aws_signing_config_aws";

/**
 * Bind a Python AwsSigningConfig to a native aws_signing_config_aws.
 */
struct config_binding {
    struct aws_signing_config_aws native;

    struct aws_byte_buf string_storage;

    /**
     * Python objects that must outlive this.
     * These all wrap values referenced from the native aws_signing_config_aws.
     * For example, the python AwsCredentialsProvider whose native resource is referenced by
     * native.credentials_provider. These values are never NULL (unless construction failed), they are Py_None if they
     * are not valid.
     */

    PyObject *py_credentials_provider;
    PyObject *py_date; /* Store original value so that user doesn't see different timezone after set/get */
    PyObject *py_should_sign_header_fn;
};

static void s_signing_config_capsule_destructor(PyObject *py_capsule) {
    struct config_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_signing_config);

    aws_byte_buf_clean_up(&binding->string_storage);

    Py_XDECREF(binding->py_credentials_provider);
    Py_XDECREF(binding->py_should_sign_header_fn);
    Py_XDECREF(binding->py_date);
}

static bool s_should_sign_header(const struct aws_byte_cursor *name, void *userdata) {
    bool should_sign = true;
    struct config_binding *binding = userdata;
    AWS_FATAL_ASSERT(binding->py_should_sign_header_fn != Py_None);

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return should_sign; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *py_result = PyObject_CallFunction(binding->py_should_sign_header_fn, "(s#)", name->ptr, name->len);
    if (py_result) {
        should_sign = PyObject_IsTrue(py_result);
        Py_DECREF(py_result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/

    return should_sign;
}

PyObject *aws_py_signing_config_new(PyObject *self, PyObject *args) {
    (void)self;

    int algorithm;
    int signature_type;
    PyObject *py_credentials_provider;
    struct aws_byte_cursor region;
    struct aws_byte_cursor service;
    PyObject *py_date;
    double timestamp;
    PyObject *py_should_sign_header_fn;
    PyObject *py_use_double_uri_encode;
    PyObject *py_should_normalize_uri_path;
    int signed_body_value_type;
    int signed_body_header_type;
    uint64_t expiration_in_seconds;
    PyObject *py_omit_session_token;
    if (!PyArg_ParseTuple(
            args,
            "iiOs#s#OdOOOiiKO",
            &algorithm,
            &signature_type,
            &py_credentials_provider,
            &region.ptr,
            &region.len,
            &service.ptr,
            &service.len,
            &py_date,
            &timestamp,
            &py_should_sign_header_fn,
            &py_use_double_uri_encode,
            &py_should_normalize_uri_path,
            &signed_body_value_type,
            &signed_body_header_type,
            &expiration_in_seconds,
            &py_omit_session_token)) {

        return NULL;
    }

    struct config_binding *binding = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct config_binding));
    if (!binding) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    PyObject *py_capsule = PyCapsule_New(binding, s_capsule_name_signing_config, s_signing_config_capsule_destructor);
    if (!py_capsule) {
        aws_mem_release(aws_py_get_allocator(), binding);
        return NULL;
    }

    /* set primitive types */
    binding->native.config_type = AWS_SIGNING_CONFIG_AWS;
    binding->native.algorithm = algorithm;
    binding->native.signature_type = signature_type;
    binding->native.flags.use_double_uri_encode = PyObject_IsTrue(py_use_double_uri_encode);
    binding->native.flags.should_normalize_uri_path = PyObject_IsTrue(py_should_normalize_uri_path);
    binding->native.signed_body_value = signed_body_value_type;
    binding->native.signed_body_header = signed_body_header_type;
    binding->native.expiration_in_seconds = expiration_in_seconds;
    binding->native.flags.omit_session_token = PyObject_IsTrue(py_omit_session_token);

    /* credentials_provider */
    binding->native.credentials_provider = aws_py_get_credentials_provider(py_credentials_provider);
    if (!binding->native.credentials_provider) {
        goto error;
    }
    binding->py_credentials_provider = py_credentials_provider;
    Py_INCREF(binding->py_credentials_provider);

    /* strings: service, region */
    size_t total_string_len;
    if (aws_add_size_checked(region.len, service.len, &total_string_len)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    if (aws_byte_buf_init(&binding->string_storage, aws_py_get_allocator(), total_string_len)) {
        PyErr_SetAwsLastError();
        goto error;
    }

    binding->native.region.ptr = binding->string_storage.buffer + binding->string_storage.len;
    binding->native.region.len = region.len;
    aws_byte_buf_write_from_whole_cursor(&binding->string_storage, region);

    binding->native.service.ptr = binding->string_storage.buffer + binding->string_storage.len;
    binding->native.service.len = service.len;
    aws_byte_buf_write_from_whole_cursor(&binding->string_storage, service);

    /* date: store original datetime python object so user doesn't see different timezones after set/get */
    aws_date_time_init_epoch_secs(&binding->native.date, timestamp);
    binding->py_date = py_date;
    Py_INCREF(binding->py_date);

    /* should_sign_header */
    if (py_should_sign_header_fn == Py_None) {
        binding->native.should_sign_header = NULL;
        binding->native.should_sign_header_ud = NULL;
    } else {
        binding->native.should_sign_header = s_should_sign_header;
        binding->native.should_sign_header_ud = binding;
    }
    binding->py_should_sign_header_fn = py_should_sign_header_fn;
    Py_INCREF(binding->py_should_sign_header_fn);

    /* success! */
    return py_capsule;

error:
    Py_DECREF(py_capsule);
    return NULL;
}

struct aws_signing_config_aws *aws_py_get_signing_config(PyObject *py_signing_config) {
    AWS_PY_RETURN_NATIVE_REF_FROM_BINDING(
        py_signing_config, s_capsule_name_signing_config, "AwsSigningConfig", config_binding);
}

/**
 * Common start to every getter. Parse arguments and return binding.
 */
static struct config_binding *s_common_get(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {
        return NULL;
    }

    struct config_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_signing_config);
    return binding;
}

PyObject *aws_py_signing_config_get_algorithm(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyLong_FromLong(binding->native.algorithm);
}

PyObject *aws_py_signing_config_get_signature_type(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyLong_FromLong(binding->native.signature_type);
}

PyObject *aws_py_signing_config_get_credentials_provider(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_credentials_provider);
    return binding->py_credentials_provider;
}

PyObject *aws_py_signing_config_get_region(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyString_FromAwsByteCursor(&binding->native.region);
}

PyObject *aws_py_signing_config_get_service(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyString_FromAwsByteCursor(&binding->native.service);
}

PyObject *aws_py_signing_config_get_date(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_date);
    return binding->py_date;
}

PyObject *aws_py_signing_config_get_use_double_uri_encode(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyBool_FromLong(binding->native.flags.use_double_uri_encode);
}

PyObject *aws_py_signing_config_get_should_normalize_uri_path(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyBool_FromLong(binding->native.flags.should_normalize_uri_path);
}

PyObject *aws_py_signing_config_get_signed_body_value_type(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyLong_FromLong(binding->native.signed_body_value);
}

PyObject *aws_py_signing_config_get_signed_body_header_type(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyLong_FromLong(binding->native.signed_body_header);
}

PyObject *aws_py_signing_config_get_expiration_in_seconds(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyLong_FromUnsignedLongLong(binding->native.expiration_in_seconds);
}

PyObject *aws_py_signing_config_get_omit_session_token(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyBool_FromLong(binding->native.flags.omit_session_token);
}
