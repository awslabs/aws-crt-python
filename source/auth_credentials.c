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
    aws_credentials_destroy(credentials);
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

    struct aws_credentials *credentials = aws_credentials_new_from_cursors(
        aws_py_get_allocator(), &access_key_id, &secret_access_key, session_token.ptr ? &session_token : NULL);
    if (!credentials) {
        return PyErr_AwsLastError();
    }

    PyObject *capsule = PyCapsule_New(credentials, s_capsule_name_credentials, s_credentials_capsule_destructor);
    if (!capsule) {
        aws_credentials_destroy(credentials);
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

    const struct aws_string *str;
    switch (member) {
        case CREDENTIALS_MEMBER_ACCESS_KEY_ID:
            str = credentials->access_key_id;
            break;
        case CREDENTIALS_MEMBER_SECRET_ACCESS_KEY:
            str = credentials->secret_access_key;
            break;
        case CREDENTIALS_MEMBER_SESSION_TOKEN:
            str = credentials->session_token;
            break;
        default:
            AWS_FATAL_ASSERT(0);
    }

    if (!str) {
        Py_RETURN_NONE;
    }

    return PyString_FromAwsString(str);
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
    struct credentials_provider_binding *provider = PyCapsule_GetPointer(capsule, s_capsule_name_credentials_provider);

    /* Note that destructor might run due to setup failing, and some/all members might still be NULL. */
    if (provider->native) {
        /* Release the credentials provider, the bindings will be cleaned up by the shutdown-complete callback. */
        aws_credentials_provider_release(provider->native);
        provider->native = NULL;
    } else {
        /* Finish clean-up immediately */
        s_credentials_provider_binding_clean_up(provider);
    }
}

struct aws_credentials_provider *aws_py_get_credentials_provider(PyObject *credentials_provider) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        credentials_provider,
        s_capsule_name_credentials_provider,
        "AwsCredentialsProviderBase",
        credentials_provider_binding);
}

static int s_aws_string_to_cstr_and_ssize(
    const struct aws_string *source,
    const char **out_cstr,
    Py_ssize_t *out_ssize) {

    *out_cstr = NULL;
    *out_ssize = 0;
    if (source) {
        if (source->len > PY_SSIZE_T_MAX) {
            return aws_raise_error(AWS_ERROR_OVERFLOW_DETECTED);
        }
        *out_cstr = aws_string_c_str(source);
        *out_ssize = source->len;
    }
    return AWS_OP_SUCCESS;
}

/* Completion callback for get_credentials() */
static void s_on_get_credentials_complete(struct aws_credentials *credentials, void *user_data) {
    PyObject *on_complete_cb = user_data;

    /* NOTE: This callback doesn't currently supply an error_code, but it should. */
    int error_code = AWS_ERROR_UNKNOWN;

    const char *access_key_id = NULL;
    Py_ssize_t access_key_id_len = 0;
    const char *secret_access_key = NULL;
    Py_ssize_t secret_access_key_len = 0;
    const char *session_token = NULL;
    Py_ssize_t session_token_len = 0;

    if (credentials) {
        error_code = AWS_ERROR_SUCCESS;

        if (s_aws_string_to_cstr_and_ssize(credentials->access_key_id, &access_key_id, &access_key_id_len)) {
            error_code = aws_last_error();
        }
        if (s_aws_string_to_cstr_and_ssize(
                credentials->secret_access_key, &secret_access_key, &secret_access_key_len)) {
            error_code = aws_last_error();
        }
        if (s_aws_string_to_cstr_and_ssize(credentials->session_token, &session_token, &session_token_len)) {
            error_code = aws_last_error();
        }
    }

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state = PyGILState_Ensure();

    PyObject *result = PyObject_CallFunction(
        on_complete_cb,
        "(is#s#s#)",
        error_code,
        access_key_id,
        access_key_id_len,
        secret_access_key,
        secret_access_key_len,
        session_token,
        session_token_len);
    if (result) {
        Py_DECREF(result);
    } else {
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    Py_DECREF(on_complete_cb);

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
