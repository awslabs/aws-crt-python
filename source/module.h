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

#define PY_SSIZE_T_CLEAN 1
#include <Python.h>

#include <aws/common/common.h>

#if PY_MAJOR_VERSION >= 3
#define PyString_FromStringAndSize PyUnicode_FromStringAndSize
#else
#endif /* PY_MAJOR_VERSION */

/* AWS Specific Helpers */
#define PyBool_FromAwsResult(result) PyBool_FromLong((result) == AWS_OP_SUCCESS)
#define PyString_FromAwsByteCursor(cursor) PyString_FromStringAndSize((const char *)(cursor).ptr, (cursor).len)

/** NOTE: May only be used while the GIL is held */
struct aws_allocator *mqtt_get_python_allocator(void);

bool is_on_python_thread(void);
