/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "common.h"

#include <aws/common/system_info.h>
#include <aws/common/thread.h>
#include <aws/s3/s3.h>

const char *s_capsule_name_sys_env = "aws_system_environment";

PyObject *aws_py_get_cpu_group_count(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    uint16_t count = aws_get_cpu_group_count();
    return PyLong_FromUnsignedLong(count);
}

PyObject *aws_py_get_cpu_count_for_group(PyObject *self, PyObject *args) {
    (void)self;

    uint16_t group_idx;
    if (!PyArg_ParseTuple(args, "H", &group_idx)) {
        return NULL;
    }

    size_t count = aws_get_cpu_count_for_group(group_idx);
    return PyLong_FromSize_t(count);
}

static void s_sys_env_destructor(PyObject *sys_env_capsule) {
    assert(PyCapsule_CheckExact(sys_env_capsule));

    struct aws_system_environment *env = PyCapsule_GetPointer(sys_env_capsule, s_capsule_name_sys_env);
    assert(env);

    aws_system_environment_destroy(env);
}

PyObject *aws_py_load_system_environment(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_system_environment *env = aws_system_environment_load(allocator);

    if (!env) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule = PyCapsule_New(env, s_capsule_name_sys_env, s_sys_env_destructor);
    if (capsule == NULL) {
        aws_system_environment_destroy(env);
        return NULL;
    }

    return capsule;
}

PyObject *aws_py_is_env_ec2(PyObject *self, PyObject *args) {
    PyObject *env_capsule = NULL;
    if (!PyArg_ParseTuple(args, "O", &env_capsule)) {
        return NULL;
    }

    struct aws_system_environment *env = PyCapsule_GetPointer(env_capsule, s_capsule_name_sys_env);
    if (!env) {
        return NULL;
    }

    if (aws_s3_is_running_on_ec2(env)) {
        Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}

PyObject *aws_py_get_ec2_instance_type(PyObject *self, PyObject *args) {
    PyObject *env_capsule = NULL;
    if (!PyArg_ParseTuple(args, "O", &env_capsule)) {
        return NULL;
    }

    struct aws_system_environment *env = PyCapsule_GetPointer(env_capsule, s_capsule_name_sys_env);
    if (!env) {
        return NULL;
    }

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_string *instance_type = aws_s3_get_ec2_instance_type(allocator, env);

    if (instance_type) {
        PyObject *ret_value = PyUnicode_FromAwsString(instance_type);
        aws_string_destroy(instance_type);
        return ret_value;
    }

    return NULL;
}

PyObject *aws_py_is_crt_s3_optimized_for_system(PyObject *self, PyObject *args) {
    PyObject *env_capsule = NULL;
    const char *instance_type_str = NULL;
    Py_ssize_t instance_type_str_len = 0;

    if (!PyArg_ParseTuple(args, "Oz#", &env_capsule, &instance_type_str, &instance_type_str_len)) {
        return NULL;
    }

    struct aws_system_environment *env = PyCapsule_GetPointer(env_capsule, s_capsule_name_sys_env);
    if (!env) {
        return PyErr_AwsLastError();
    }

    struct aws_byte_cursor *instance_type_to_pass = NULL;
    struct aws_byte_cursor instance_type_cur;

    if (instance_type_str_len > 0) {
        instance_type_cur = aws_byte_cursor_from_array(instance_type_str, (size_t)instance_type_str_len);
        instance_type_to_pass = &instance_type_cur;
    }

    bool is_optimized = aws_s3_is_optimized_for_system_env(env, instance_type_to_pass);

    if (is_optimized) {
        Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}

PyObject *aws_py_thread_join_all_managed(PyObject *self, PyObject *args) {
    (void)self;

    double timeout_sec = 0.0;
    if (!PyArg_ParseTuple(args, "d", &timeout_sec)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }

    /* Actual call uses 0 to denote "wait forever" */
    uint64_t timeout_ns;
    if (timeout_sec < 0.0) {
        timeout_ns = 0;
    } else {
        timeout_ns = (uint64_t)(timeout_sec * 1000000000);
        if (timeout_ns == 0) {
            timeout_ns = 1;
        }
    }
    aws_thread_set_managed_join_timeout_ns(timeout_ns);

    if (aws_thread_join_all_managed()) {
        Py_RETURN_FALSE;
    }

    Py_RETURN_TRUE;
}
