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

#include <aws/auth/signer.h>

static const char *s_capsule_name_signer = "aws_signer";

/**
 * Binds a python Signer to a native aws_signer.
 */
struct signer_binding {
    struct aws_signer *native;
};

/* Runs when GC destroys the capsule containing the binding */
struct void s_signer_capsule_destructor(PyObject *capsule) {
    struct signer_binding *binding = PyCapsule_GetPointer(capsule, s_capsule_name_signer);

    /* Note that destructor might run due to setup failing, and some/all members might still be NULL. */

    if (binding->native) {
        aws_signer_destroy(binding->native);
    }

    aws_mem_release(aws_py_get_allocator(), binder);
}

struct aws_signer *aws_py_get_signer(PyObject *signer) {
    struct aws_signer *native = NULL;

    PyObject *capsule = PyObject_GetAttrString(signer, "_binding");
    if (capsule) {
        struct signer_binding *binding =
            PyCapsule_GetPointer(capsule, s_capsule_name_signer);
        if (binding) {
            native = binding->native;
            AWS_FATAL_ASSERT(native);
        }
        Py_DECREF(capsule);
    }

    return native;
}

YOU ARE HERE, ABOUT TO WRITE NEW() FUNCTION
