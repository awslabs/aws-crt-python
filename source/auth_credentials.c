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

#include "io.h"

#include <aws/auth/credentials.h>
#include <aws/common/string.h>

static const char *s_capsule_name_credentials = "aws_credentials";
static const char *s_capsule_name_credentials_provider = "aws_credentials_provider";

/* Credentials capsule contains raw aws_credentials struct. There is no intermediate binding struct. */

static void s_credentials_capsule_destructor(PyObject *capsule) {
    struct aws_credentials *credentials = PyCapsule_GetPointer(capsule, s_capsule_name_credentials);
    aws_credentials_release(credentials);
}

PyObject *aws_py_credentials_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor access_key_id;
    struct aws_byte_cursor secret_access_key;
    struct aws_byte_cursor session_token; /* session_token is optional */
    if (!PyArg_ParseTuple(
            args,
            "s#s#z#",
            &access_key_id.ptr,
            &access_key_id.len,
            &secret_access_key.ptr,
            &secret_access_key.len,
            &session_token.ptr,
            &session_token.len)) {
        return NULL;
    }

    struct aws_credentials *credentials = aws_credentials_new(
        aws_py_get_allocator(),
        access_key_id,
        secret_access_key,
        session_token,
        UINT64_MAX /*expiration_timepoint_seconds*/);
    if (!credentials) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule = PyCapsule_New(credentials, s_capsule_name_credentials, s_credentials_capsule_destructor);
    if (!capsule) {
        aws_credentials_release(credentials);
        return NULL;
    }

    return capsule;
}

struct aws_credentials *aws_py_get_credentials(PyObject *credentials) {
    return aws_py_get_binding(credentials, s_capsule_name_credentials, "AwsCredentials");
}

enum credentials_member {
    CREDENTIALS_MEMBER_ACCESS_KEY_ID,
    CREDENTIALS_MEMBER_SECRET_ACCESS_KEY,
    CREDENTIALS_MEMBER_SESSION_TOKEN,
};

static PyObject *s_credentials_get_member_str(PyObject *args, enum credentials_member member) {
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) {
        return NULL;
    }

    const struct aws_credentials *credentials = PyCapsule_GetPointer(capsule, s_capsule_name_credentials);
    if (!credentials) {
        return NULL;
    }

    struct aws_byte_cursor cursor;
    switch (member) {
        case CREDENTIALS_MEMBER_ACCESS_KEY_ID:
            cursor = aws_credentials_get_access_key_id(credentials);
            break;
        case CREDENTIALS_MEMBER_SECRET_ACCESS_KEY:
            cursor = aws_credentials_get_secret_access_key(credentials);
            break;
        case CREDENTIALS_MEMBER_SESSION_TOKEN:
            cursor = aws_credentials_get_session_token(credentials);
            break;
        default:
            AWS_FATAL_ASSERT(0);
    }

    if (member == CREDENTIALS_MEMBER_SESSION_TOKEN && cursor.len == 0) {
        Py_RETURN_NONE;
    }

    return PyUnicode_FromAwsByteCursor(&cursor);
}

PyObject *aws_py_credentials_access_key_id(PyObject *self, PyObject *args) {
    (void)self;
    return s_credentials_get_member_str(args, CREDENTIALS_MEMBER_ACCESS_KEY_ID);
}

PyObject *aws_py_credentials_secret_access_key(PyObject *self, PyObject *args) {
    (void)self;
    return s_credentials_get_member_str(args, CREDENTIALS_MEMBER_SECRET_ACCESS_KEY);
}

PyObject *aws_py_credentials_session_token(PyObject *self, PyObject *args) {
    (void)self;
    return s_credentials_get_member_str(args, CREDENTIALS_MEMBER_SESSION_TOKEN);
}

/**
 * Binds a Python CredentialsProvider to a native aws_credentials_provider.
 */
struct credentials_provider_binding {
    struct aws_credentials_provider *native;

    /* Dependencies that must outlive this.
     * Note that different types of providers have different dependencies */
    PyObject *bootstrap;
};

/* Finally clean up binding (after capsule destructor runs and credentials provider shutdown completes) */
static void s_credentials_provider_binding_clean_up(struct credentials_provider_binding *binding) {
    Py_XDECREF(binding->bootstrap);
    aws_mem_release(aws_py_get_allocator(), binding);
}

/* Runs after the credentials provider has finished shutting down */
static void s_credentials_provider_shutdown_complete(void *user_data) {
    s_credentials_provider_binding_clean_up(user_data);
}

/* Runs when the GC destroys the capsule containing the binding */
static void s_credentials_provider_capsule_destructor(PyObject *capsule) {
    struct credentials_provider_binding *binding = PyCapsule_GetPointer(capsule, s_capsule_name_credentials_provider);

    /* Note that destructor might run due to setup failing, and some/all members might still be NULL. */
    if (binding->native) {
        /* Release the credentials provider, the binding will be cleaned up by the shutdown-complete callback.
         * Note that binding might be deleted as an immediate side-effect of this call, so don't touch it anymore. */
        aws_credentials_provider_release(binding->native);
    } else {
        /* Finish clean-up immediately */
        s_credentials_provider_binding_clean_up(binding);
    }
}

struct aws_credentials_provider *aws_py_get_credentials_provider(PyObject *credentials_provider) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        credentials_provider,
        s_capsule_name_credentials_provider,
        "AwsCredentialsProviderBase",
        credentials_provider_binding);
}

/* Completion callback for get_credentials() */
static void s_on_get_credentials_complete(struct aws_credentials *credentials, int error_code, void *user_data) {
    PyObject *on_complete_cb = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Create capsule to reference these aws_credentials */
    PyObject *capsule = NULL;
    if (!error_code) {
        AWS_FATAL_ASSERT(credentials);

        capsule = PyCapsule_New(credentials, s_capsule_name_credentials, s_credentials_capsule_destructor);
        if (capsule) {
            aws_credentials_acquire(credentials);
        } else {
            /* Unlikely, but if PyCapsule_New() raises exception, we still need to fire completion callback.
             * So we'll translate python exception to AWS error_code and pass that. */
            aws_py_raise_error();
            error_code = aws_last_error();
        }
    }

    if (capsule == NULL) {
        capsule = Py_None;
        Py_INCREF(capsule);
    }

    PyObject *result = PyObject_CallFunction(on_complete_cb, "(iO)", error_code, capsule);
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    Py_DECREF(on_complete_cb);
    Py_DECREF(capsule);

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

PyObject *aws_py_credentials_provider_get_credentials(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *capsule;
    PyObject *on_complete_cb;
    if (!PyArg_ParseTuple(args, "OO", &capsule, &on_complete_cb)) {
        return NULL;
    }

    struct credentials_provider_binding *provider = PyCapsule_GetPointer(capsule, s_capsule_name_credentials_provider);
    if (!provider) {
        return NULL;
    }

    AWS_FATAL_ASSERT(on_complete_cb != Py_None);

    Py_INCREF(on_complete_cb);
    if (aws_credentials_provider_get_credentials(provider->native, s_on_get_credentials_complete, on_complete_cb)) {
        Py_DECREF(on_complete_cb);
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

/* Create binding and capsule.
 * Helper function for every aws_py_credentials_provider_new_XYZ() function */
static PyObject *s_new_credentials_provider_binding_and_capsule(struct credentials_provider_binding **out_binding) {
    *out_binding = NULL;

    struct credentials_provider_binding *binding =
        aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct credentials_provider_binding));
    if (!binding) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule =
        PyCapsule_New(binding, s_capsule_name_credentials_provider, s_credentials_provider_capsule_destructor);
    if (!capsule) {
        aws_mem_release(aws_py_get_allocator(), binding);
        return NULL;
    }

    *out_binding = binding;
    return capsule;
}

PyObject *aws_py_credentials_provider_new_chain_default(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *bootstrap_py;
    if (!PyArg_ParseTuple(args, "O", &bootstrap_py)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct credentials_provider_binding *binding;
    PyObject *capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    binding->bootstrap = bootstrap_py;
    Py_INCREF(binding->bootstrap);

    struct aws_credentials_provider_chain_default_options options = {
        .bootstrap = bootstrap,
        .shutdown_options = {s_credentials_provider_shutdown_complete, binding},
    };

    binding->native = aws_credentials_provider_new_chain_default(aws_py_get_allocator(), &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;

error:
    Py_DECREF(capsule);
    return NULL;
}

PyObject *aws_py_credentials_provider_new_static(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_byte_cursor access_key_id;
    struct aws_byte_cursor secret_access_key;
    struct aws_byte_cursor session_token; /* optional */
    if (!PyArg_ParseTuple(
            args,
            "s#s#z#",
            &access_key_id.ptr,
            &access_key_id.len,
            &secret_access_key.ptr,
            &secret_access_key.len,
            &session_token.ptr,
            &session_token.len)) {
        return NULL;
    }

    struct credentials_provider_binding *binding;
    PyObject *capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    struct aws_credentials_provider_static_options options = {
        .access_key_id = access_key_id,
        .secret_access_key = secret_access_key,
        .session_token = session_token,
        .shutdown_options = {s_credentials_provider_shutdown_complete, binding},
    };

    binding->native = aws_credentials_provider_new_static(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;
error:
    Py_DECREF(capsule);
    return NULL;
}
