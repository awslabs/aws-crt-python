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

    /**
     * Python objects that must must outlive this.
     * These all wrap values referenced from the native aws_signing_config_aws.
     * For example, the python AwsCredentialsProvider whose native resource is referenced by
     * native.credentials_provider. These values are never NULL (unless construction failed), they are Py_None if they
     * are not valid.
     */

    PyObject *py_credentials_provider;
    PyObject *py_should_sign_param_fn;
    PyObject *py_region_str;
    PyObject *py_service_str;
    PyObject *py_date; /* Store original value so that user doesn't see different timezone after set/get */
};

static void s_signing_config_capsule_destructor(PyObject *py_capsule) {
    struct config_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_signing_config);

    Py_XDECREF(binding->py_credentials_provider);
    Py_XDECREF(binding->py_should_sign_param_fn);
    Py_XDECREF(binding->py_region_str);
    Py_XDECREF(binding->py_service_str);
    Py_XDECREF(binding->py_date);
}

PyObject *aws_py_signing_config_new(PyObject *self, PyObject *args) {
    (void)self;

    if (!PyArg_ParseTuple(args, "")) {
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

    binding->native.config_type = AWS_SIGNING_CONFIG_AWS;
    binding->native.should_normalize_uri_path = true;
    binding->native.sign_body = true;

    binding->py_credentials_provider = Py_None;
    Py_INCREF(binding->py_credentials_provider);

    binding->py_should_sign_param_fn = Py_None;
    Py_INCREF(binding->py_should_sign_param_fn);

    binding->py_region_str = Py_None;
    Py_INCREF(binding->py_region_str);

    binding->py_service_str = Py_None;
    Py_INCREF(binding->py_service_str);

    binding->py_date = Py_None;
    Py_INCREF(binding->py_date);

    return py_capsule;
}

struct aws_signing_config_aws *aws_py_get_signing_config(PyObject *py_signing_config) {
    struct aws_signing_config_aws *native = NULL;

    PyObject *py_capsule = PyObject_GetAttrString(py_signing_config, "_binding");
    if (py_capsule) {
        struct config_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_signing_config);
        if (binding) {
            native = &binding->native;
            AWS_FATAL_ASSERT(native);
        }
        Py_DECREF(py_capsule);
    }

    return native;
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

/**
 * Common start to every setter.
 * FMT: string for PyArg_ParseTuple(). DO NOT pass the "O" for the capsule.
 * ...: varargs for PyArg_ParseTuple(). DO NOT pass &capsule.
 *
 * on error, returns NULL from function with python exception set
 * on success, creates and sets local variable: config_binding *binding = ...;
 */
#define S_COMMON_SET(FMT, ...)                                                                                         \
    (void)self;                                                                                                        \
    PyObject *py_capsule;                                                                                              \
    if (!PyArg_ParseTuple(args, "O" FMT, &py_capsule, __VA_ARGS__)) {                                                  \
        return NULL;                                                                                                   \
    }                                                                                                                  \
    struct config_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_signing_config);                  \
    if (!binding) {                                                                                                    \
        return NULL;                                                                                                   \
    }

PyObject *aws_py_signing_config_get_algorithm(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyLong_FromLong(binding->native.algorithm);
}

PyObject *aws_py_signing_config_set_algorithm(PyObject *self, PyObject *args) {
    int algorithm;
    S_COMMON_SET("i", &algorithm);
    binding->native.algorithm = algorithm;
    Py_RETURN_NONE;
}

PyObject *aws_py_signing_config_get_credentials_provider(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_credentials_provider);
    return binding->py_credentials_provider;
}

PyObject *aws_py_signing_config_set_credentials_provider(PyObject *self, PyObject *args) {
    PyObject *py_credentials_provider;
    S_COMMON_SET("O", &py_credentials_provider);

    struct aws_credentials_provider *credentials_provider = NULL;
    if (py_credentials_provider != Py_None) {
        credentials_provider = aws_py_get_credentials_provider(py_credentials_provider);
        if (!credentials_provider) {
            return NULL;
        }
    }

    binding->native.credentials_provider = credentials_provider;

    /* Swap which python object we're keeping alive */
    Py_DECREF(binding->py_credentials_provider);
    binding->py_credentials_provider = py_credentials_provider;
    Py_INCREF(binding->py_credentials_provider);

    Py_RETURN_NONE;
}

PyObject *aws_py_signing_config_get_region(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_region_str);
    return binding->py_region_str;
}

static PyObject *s_common_string_set(
    PyObject *py_new_string_value,
    PyObject **py_existing_string_ref,
    struct aws_byte_cursor *existing_cursor_ref,
    const char *errmsg) {

    struct aws_byte_cursor cursor;
    if (py_new_string_value == Py_None) {
        AWS_ZERO_STRUCT(cursor);
    } else {
        cursor = aws_byte_cursor_from_pystring(py_new_string_value);
        if (cursor.ptr == NULL) {
            PyErr_SetString(PyExc_TypeError, errmsg);
            return NULL;
        }
    }

    *existing_cursor_ref = cursor;

    /* Swap which python object we're keeping alive */
    Py_DECREF(*py_existing_string_ref);
    *py_existing_string_ref = py_new_string_value;
    Py_INCREF(*py_existing_string_ref);

    Py_RETURN_NONE;
};

PyObject *aws_py_signing_config_set_region(PyObject *self, PyObject *args) {
    PyObject *py_region_str;
    S_COMMON_SET("O", &py_region_str);

    return s_common_string_set(
        py_region_str, &binding->py_region_str, &binding->native.region, "invalid region string");
}

PyObject *aws_py_signing_config_get_service(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_service_str);
    return binding->py_service_str;
}

PyObject *aws_py_signing_config_set_service(PyObject *self, PyObject *args) {
    PyObject *py_service_str;
    S_COMMON_SET("O", &py_service_str);

    return s_common_string_set(
        py_service_str, &binding->py_service_str, &binding->native.service, "invalid service string");
}

PyObject *aws_py_signing_config_get_date(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_date);
    return binding->py_date;
}

PyObject *aws_py_signing_config_set_date(PyObject *self, PyObject *args) {
    PyObject *py_date;
    double timestamp;
    S_COMMON_SET("Od", &py_date, &timestamp);

    /* python already extracted timestamp from date, so we know it's valid */

    struct aws_date_time native_date;
    aws_date_time_init_epoch_secs(&native_date, timestamp);

    binding->native.date = native_date;

    /* Swap which python object we're keeping alive */
    Py_DECREF(binding->py_date);
    binding->py_date = py_date;
    Py_INCREF(binding->py_date);

    Py_RETURN_NONE;
}

PyObject *aws_py_signing_config_get_should_sign_param(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_should_sign_param_fn);
    return binding->py_should_sign_param_fn;
}

static bool s_should_sign_param(const struct aws_byte_cursor *name, void *userdata) {
    bool should_sign = true;
    struct config_binding *binding = userdata;
    AWS_FATAL_ASSERT(binding->py_should_sign_param_fn != Py_None);

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *py_result = PyObject_CallFunction(binding->py_should_sign_param_fn, "(s#)", name->ptr, name->len);
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

PyObject *aws_py_signing_config_set_should_sign_param(PyObject *self, PyObject *args) {
    PyObject *py_should_sign_param_fn;
    S_COMMON_SET("O", &py_should_sign_param_fn);

    if (py_should_sign_param_fn == Py_None) {
        binding->native.should_sign_param = NULL;
        binding->native.should_sign_param_ud = NULL;
    } else {
        binding->native.should_sign_param = s_should_sign_param;
        binding->native.should_sign_param_ud = binding;
    }

    /* Swap which python object we're keeping alive */
    Py_DECREF(binding->py_should_sign_param_fn);
    binding->py_should_sign_param_fn = py_should_sign_param_fn;
    Py_INCREF(binding->py_should_sign_param_fn);

    Py_RETURN_NONE;
}

PyObject *aws_py_signing_config_get_use_double_uri_encode(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyBool_FromLong(binding->native.use_double_uri_encode);
}

PyObject *aws_py_signing_config_set_use_double_uri_encode(PyObject *self, PyObject *args) {
    int use_double_uri_encode;
    S_COMMON_SET("p", &use_double_uri_encode);

    binding->native.use_double_uri_encode = use_double_uri_encode;
    Py_RETURN_NONE;
}

PyObject *aws_py_signing_config_get_should_normalize_uri_path(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyBool_FromLong(binding->native.should_normalize_uri_path);
}

PyObject *aws_py_signing_config_set_should_normalize_uri_path(PyObject *self, PyObject *args) {
    int should_normalize_uri_path;
    S_COMMON_SET("p", &should_normalize_uri_path);

    binding->native.should_normalize_uri_path = should_normalize_uri_path;
    Py_RETURN_NONE;
}

PyObject *aws_py_signing_config_get_sign_body(PyObject *self, PyObject *args) {
    struct config_binding *binding = s_common_get(self, args);
    if (!binding) {
        return NULL;
    }

    return PyBool_FromLong(binding->native.sign_body);
}

PyObject *aws_py_signing_config_set_sign_body(PyObject *self, PyObject *args) {
    int sign_body;
    S_COMMON_SET("p", &sign_body);

    binding->native.sign_body = sign_body;
    Py_RETURN_NONE;
}
