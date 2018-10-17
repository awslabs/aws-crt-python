#ifndef AWS_CRT_PYTHON_IO_H
#define AWS_CRT_PYTHON_IO_H
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
 * This file includes definitions for common aws-c-io functions.
 */

#include "module.h"

/**
 * Name string for event_loop_group capsules.
 */
extern const char *s_capsule_name_elg;

/**
 * Create a new event_loop_group to be managed by a Python Capsule.
 */
PyObject *io_new_event_loop_group(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_IO_H */
