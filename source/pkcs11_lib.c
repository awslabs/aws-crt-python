/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "io.h"

PyObject *aws_py_pkcs11_lib_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor filename;
    int behavior;
    if (!PyArg_ParseTuple(args, "s#b", &py_self)) {
        return NULL;
    }

    return NULL;
}
