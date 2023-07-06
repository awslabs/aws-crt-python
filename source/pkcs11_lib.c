/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "io.h"

#include <aws/io/pkcs11.h>

static const char *s_capsule_name = "aws_pkcs11_lib";

static void s_pkcs11_lib_capsule_destructor(PyObject *capsule) {
    struct aws_pkcs11_lib *pkcs11_lib = PyCapsule_GetPointer(capsule, s_capsule_name);
    aws_pkcs11_lib_release(pkcs11_lib);
}

struct aws_pkcs11_lib *aws_py_get_pkcs11_lib(PyObject *pkcs11_lib) {
    return aws_py_get_binding(pkcs11_lib, s_capsule_name, "Pkcs11Lib");
}

PyObject *aws_py_pkcs11_lib_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor filename;
    int behavior;
    if (!PyArg_ParseTuple(args, "s#i", &filename.ptr, &filename.len, &behavior)) {
        return NULL;
    }

    struct aws_pkcs11_lib_options options = {
        .filename = filename,
        .initialize_finalize_behavior = behavior,
    };
    struct aws_pkcs11_lib *pkcs11_lib = aws_pkcs11_lib_new(aws_py_get_allocator(), &options);
    if (pkcs11_lib == NULL) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule = PyCapsule_New(pkcs11_lib, s_capsule_name, s_pkcs11_lib_capsule_destructor);
    if (capsule == NULL) {
        aws_pkcs11_lib_release(pkcs11_lib); /* cleanup due to error */
        return NULL;
    }

    return capsule;
}
