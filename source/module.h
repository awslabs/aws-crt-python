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
#include <python3.6m/Python.h>

#include <aws/common/common.h>

struct aws_byte_buf;

#if PY_MAJOR_VERSION >= 3
#    define PyString_FromStringAndSize PyUnicode_FromStringAndSize
#    define BYTE_BUF_FORMAT_STR "y#"
#else
#    define BYTE_BUF_FORMAT_STR "s#"
#    if SIZE_MAX == UINT32_MAX
#        define PyLong_AsSize_t PyLong_AsUnsignedLong
#    elif SIZE_MAX == UINT64_MAX
#        define PyLong_AsSize_t PyLong_AsUnsignedLongLong
#    else
#        error "Unsupported architecture"
#    endif
#endif /* PY_MAJOR_VERSION */

/* AWS Specific Helpers */
#define PyBool_FromAwsResult(result) PyBool_FromLong((result) == AWS_OP_SUCCESS)
#define PyString_FromAwsByteCursor(cursor) PyString_FromStringAndSize((const char *)(cursor)->ptr, (cursor)->len)

int PyIntEnum_Check(PyObject *int_enum_obj);
long PyIntEnum_AsLong(PyObject *int_enum_obj);

struct aws_byte_cursor aws_byte_cursor_from_pystring(PyObject *str);

/* Set current thread's error indicator based on aws_last_error() */
void PyErr_SetAwsLastError(void);

/* Set current thread's error indicator based on aws_last_error() and returns NULL */
PyObject *PyErr_AwsLastError(void);

PyObject *aws_py_memory_view_from_byte_buffer(struct aws_byte_buf *buf, int flags);

/* Allocator that calls into PyObject_[Malloc|Free|Realloc] */
struct aws_allocator *aws_crt_python_get_allocator(void);

#endif /* AWS_CRT_PYTHON_MODULE_H */
