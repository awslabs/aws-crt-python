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
        return PyErr_AwsLastError();
    }

    struct aws_system_environment *env = PyCapsule_GetPointer(env_capsule, s_capsule_name_sys_env);
    if (!env) {
        return PyErr_AwsLastError();
    }
    
    struct aws_byte_cursor system_virt_name = aws_system_environment_get_virtualization_vendor(env);
    
    if (aws_byte_cursor_eq_c_str_ignore_case(&system_virt_name, "amazon ec2")) {
        Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}

PyObject *aws_py_get_ec2_instance_type(PyObject *self, PyObject *args) {
    PyObject *env_capsule = NULL;
    if (!PyArg_ParseTuple(args, "O", &env_capsule)) {
        return PyErr_AwsLastError();
    }

    struct aws_system_environment *env = PyCapsule_GetPointer(env_capsule, s_capsule_name_sys_env);
    if (!env) {
        return PyErr_AwsLastError();
    }
    
    struct aws_byte_cursor product_name = aws_system_environment_get_virtualization_product_name(env);
    
    return PyUnicode_FromAwsByteCursor(&product_name);
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
