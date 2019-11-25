#ifndef AWS_CRT_PYTHON_MODULE_H
#define AWS_CRT_PYTHON_MODULE_H
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

/**
 * This file contains general helpers.
 */

#define PY_SSIZE_T_CLEAN 1
#include <Python.h>

#include <aws/common/common.h>

struct aws_byte_buf;
struct aws_string;

#if PY_MAJOR_VERSION >= 3
#    define PyString_FromStringAndSize PyUnicode_FromStringAndSize
#    define PyString_FromString PyUnicode_FromString
#    define READABLE_BYTES_FORMAT_STR "y#"
#else
#    define READABLE_BYTES_FORMAT_STR "s#"
#endif /* PY_MAJOR_VERSION */

/* AWS Specific Helpers */
#define PyBool_FromAwsResult(result) PyBool_FromLong((result) == AWS_OP_SUCCESS)
#define PyString_FromAwsByteCursor(cursor) PyString_FromStringAndSize((const char *)(cursor)->ptr, (cursor)->len)
PyObject *PyString_FromAwsString(const struct aws_string *aws_str);

int PyIntEnum_Check(PyObject *int_enum_obj);
long PyIntEnum_AsLong(PyObject *int_enum_obj);

/* Python 2/3 compatible check. Return whether object is a PyLong (OR PyInt in python2). */
int PyLongOrInt_Check(PyObject *obj);

/* Create cursor from PyString, PyBytes, or PyUnicode.
 * If conversion cannot occur, cursor->ptr will be NULL but no python exception is set */
struct aws_byte_cursor aws_byte_cursor_from_pystring(PyObject *str);

/* Set current thread's error indicator based on aws_last_error() */
void PyErr_SetAwsLastError(void);

/* Set current thread's error indicator based on aws_last_error() and returns NULL */
PyObject *PyErr_AwsLastError(void);

/**
 * Raise an AWS error corresponding to the current Python error.
 *
 * Prints the current Python error to stderr and clears the Python error indicator.
 * Finds an AWS error code corresponding to the current Python error (fallback is AWS_ERROR_UNKNOWN).
 * Invokes aws_raise_error() with that error code and always returns AWS_OP_ERR.
 *
 * The Python error indicator MUST be set and the GIL MUST be held when calling this function. */
int aws_py_raise_error(void);

/**
 * Return built-in Python exception type corresponding to an AWS_ERROR_ code.
 * Ex: AWS_ERROR_OOM -> MemoryError.
 * Returns None if there is no match.
 */
PyObject *aws_py_get_corresponding_builtin_exception(PyObject *self, PyObject *args);

PyObject *aws_py_get_error_name(PyObject *self, PyObject *args);
PyObject *aws_py_get_error_message(PyObject *self, PyObject *args);

/* Create a write-only memoryview from the remaining free space in an aws_byte_buf */
PyObject *aws_py_memory_view_from_byte_buffer(struct aws_byte_buf *buf);

/* Allocator that calls into PyObject_[Malloc|Free|Realloc] */
struct aws_allocator *aws_py_get_allocator(void);

/* Return the capsule ptr from obj._binding
 * On error, NULL is returned and a python exception is set. */
void *aws_py_get_binding(PyObject *obj, const char *capsule_name, const char *class_name);

/* Contents of aws_py_get_XYZ() function where obj._binding->native is returned.
 * NOTE: only works where native is stored by ptr. */
#define AWS_PY_RETURN_NATIVE_FROM_BINDING(PYOBJ, CAPSULE_NAME, CLASS_NAME, BINDING_TYPE)                               \
    struct BINDING_TYPE *binding = aws_py_get_binding((PYOBJ), (CAPSULE_NAME), (CLASS_NAME));                          \
    if (binding) {                                                                                                     \
        if (binding->native) {                                                                                         \
            return binding->native;                                                                                    \
        }                                                                                                              \
        PyErr_Format(PyExc_TypeError, "Expected valid '%s', but '_binding.native' is NULL", (CLASS_NAME));             \
    }                                                                                                                  \
    return NULL

/* Shorthand for `return &obj._binding->native;` */
#define AWS_PY_RETURN_NATIVE_REF_FROM_BINDING(PYOBJ, CAPSULE_NAME, CLASS_NAME, BINDING_TYPE)                           \
    struct BINDING_TYPE *binding = aws_py_get_binding((PYOBJ), (CAPSULE_NAME), (CLASS_NAME));                          \
    if (!binding) {                                                                                                    \
        return NULL;                                                                                                   \
    }                                                                                                                  \
    return &binding->native

#endif /* AWS_CRT_PYTHON_MODULE_H */
