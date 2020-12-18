/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
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
    PyObject *py_provider;
};

/* Finally clean up binding (after capsule destructor runs and credentials provider shutdown completes) */
static void s_credentials_provider_binding_clean_up(struct credentials_provider_binding *binding) {
    if (binding->py_provider) {
        Py_XDECREF(binding->py_provider);
    }
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

PyObject *aws_py_credentials_provider_new_profile(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py;
    struct aws_byte_cursor profile_name;
    struct aws_byte_cursor config_file_name;
    struct aws_byte_cursor credentials_file_name;

    if (!PyArg_ParseTuple(
            args,
            "Oz#z#z#",
            &bootstrap_py,
            &profile_name.ptr,
            &profile_name.len,
            &config_file_name.ptr,
            &config_file_name.len,
            &credentials_file_name.ptr,
            &credentials_file_name.len)) {
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

    struct aws_credentials_provider_profile_options options = {
        .bootstrap = bootstrap,
        .profile_name_override = profile_name,
        .config_file_name_override = config_file_name,
        .credentials_file_name_override = credentials_file_name,
        .shutdown_options =
            {
                .shutdown_callback = s_credentials_provider_shutdown_complete,
                .shutdown_user_data = binding,
            },
    };

    binding->native = aws_credentials_provider_new_profile(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;
error:
    Py_DECREF(capsule);
    return NULL;
}

PyObject *aws_py_credentials_provider_new_process(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_byte_cursor profile_to_use;

    if (!PyArg_ParseTuple(args, "z#", &profile_to_use.ptr, &profile_to_use.len)) {
        return NULL;
    }

    struct credentials_provider_binding *binding;
    PyObject *capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    struct aws_credentials_provider_process_options options = {
        .profile_to_use = profile_to_use,
        .shutdown_options =
            {
                .shutdown_callback = s_credentials_provider_shutdown_complete,
                .shutdown_user_data = binding,
            },
    };

    binding->native = aws_credentials_provider_new_process(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;
error:
    Py_DECREF(capsule);
    return NULL;
}

PyObject *aws_py_credentials_provider_new_environment(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct credentials_provider_binding *binding;
    PyObject *capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    struct aws_credentials_provider_environment_options options = {
        .shutdown_options =
            {
                .shutdown_callback = s_credentials_provider_shutdown_complete,
                .shutdown_user_data = binding,
            },
    };

    binding->native = aws_credentials_provider_new_environment(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;
error:
    Py_DECREF(capsule);
    return NULL;
}

PyObject *aws_py_credentials_provider_new_chain(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *providers_arg;

    if (!PyArg_ParseTuple(args, "O", &providers_arg)) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */
    bool success = false;
    PyObject *providers_pyseq = NULL;
    struct aws_credentials_provider **providers_carray = NULL;
    PyObject *capsule = NULL;

    /* Need temporary C-array of pointers to underlying aws_credentials_provider structs */
    providers_pyseq = PySequence_Fast(providers_arg, "Expected sequence of AwsCredentialsProviders");
    if (!providers_pyseq) {
        goto done;
    }
    size_t provider_count = (size_t)PySequence_Fast_GET_SIZE(providers_pyseq);
    if (provider_count == 0) {
        PyErr_SetString(PyExc_ValueError, "Must supply at least one AwsCredentialsProvider.");
        goto done;
    }

    providers_carray = aws_mem_calloc(allocator, provider_count, sizeof(void *));
    if (!providers_carray) {
        PyErr_SetAwsLastError();
        goto done;
    }

    for (size_t i = 0; i < provider_count; ++i) {
        PyObject *provider_py = PySequence_Fast_GET_ITEM(providers_pyseq, i);
        providers_carray[i] = aws_py_get_credentials_provider(provider_py);
        if (!providers_carray[i]) {
            goto done;
        }
    }

    struct credentials_provider_binding *binding;
    capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        goto done;
    }

    struct aws_credentials_provider_chain_options options = {
        .provider_count = provider_count,
        .providers = providers_carray,
        .shutdown_options =
            {
                .shutdown_callback = s_credentials_provider_shutdown_complete,
                .shutdown_user_data = binding,
            },
    };

    binding->native = aws_credentials_provider_new_chain(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;

done:
    Py_XDECREF(providers_pyseq);
    aws_mem_release(allocator, providers_carray);

    if (success) {
        return capsule;
    }

    Py_XDECREF(capsule);
    return NULL;
}

static int s_credentials_provider_py_provider_get_credentials(
    struct aws_credentials_provider *provider,
    aws_on_get_credentials_callback_fn callback,
    void *user_data) {
    struct aws_allocator *allocator = provider->allocator;

    struct aws_string *access_key_id = NULL;
    struct aws_string *secret_access_key = NULL;
    struct aws_string *session_token = NULL;
    struct aws_credentials *credentials = NULL;
    int error_code = AWS_ERROR_SUCCESS;
    struct credentials_provider_binding *binding = provider->impl;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *dict = PyObject_CallMethod(binding->py_provider, "get_credential", "()");

    PyObject *py_key = PyDict_GetItemString(dict, "AccessKeyId");
    PyObject *py_secret_key = PyDict_GetItemString(dict, "SecretAccessKey");
    PyObject *py_token = PyDict_GetItemString(dict, "SessionToken");
    PyObject *py_expiration = PyDict_GetItemString(dict, "Expiration");

    struct aws_byte_cursor cursor;
    if (py_key) {
        cursor = aws_byte_cursor_from_pyunicode(py_key);
        access_key_id = aws_string_new_from_cursor(allocator, &cursor);
    }
    if (py_secret_key) {
        cursor = aws_byte_cursor_from_pyunicode(py_secret_key);
        secret_access_key = aws_string_new_from_cursor(allocator, &cursor);
    }
    if (py_token) {
        cursor = aws_byte_cursor_from_pyunicode(py_token);
        session_token = aws_string_new_from_cursor(allocator, &cursor);
    }
    uint64_t expiration = UINT64_MAX;
    if (py_expiration) {
        expiration = PyLong_AsUnsignedLongLong(py_expiration);
    }
    PyGILState_Release(state);
    if (access_key_id != NULL && secret_access_key != NULL) {
        credentials =
            aws_credentials_new_from_string(allocator, access_key_id, secret_access_key, session_token, expiration);
        if (credentials == NULL) {
            error_code = aws_last_error();
            if (!error_code) {
                error_code = AWS_AUTH_CREDENTIALS_PROVIDER_INVALID_DELEGATE;
            }
        }
    } else {
        error_code = AWS_AUTH_CREDENTIALS_PROVIDER_INVALID_DELEGATE;
    }

    callback(credentials, error_code, user_data);

    aws_credentials_release(credentials);
    aws_string_destroy(session_token);
    aws_string_destroy(secret_access_key);
    aws_string_destroy(access_key_id);

    return AWS_OP_SUCCESS;
}

static void s_credentials_provider_py_provider_destroy(struct aws_credentials_provider *provider) {
    if (provider && provider->shutdown_options.shutdown_callback) {
        provider->shutdown_options.shutdown_callback(provider->shutdown_options.shutdown_user_data);
    }

    aws_mem_release(provider->allocator, provider);
}

static struct aws_credentials_provider_vtable s_aws_credentials_provider_py_provider_vtable = {
    .get_credentials = s_credentials_provider_py_provider_get_credentials,
    .destroy = s_credentials_provider_py_provider_destroy,
};

PyObject *aws_py_credentials_provider_new_python(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *py_provider;

    if (!PyArg_ParseTuple(args, "O", &py_provider)) {
        return NULL;
    }

    struct credentials_provider_binding *binding;
    PyObject *capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        return NULL;
    }

    binding->py_provider = py_provider;
    Py_INCREF(py_provider);

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    struct aws_credentials_provider_delegate_options options = {
        .provider_vtable = &s_aws_credentials_provider_py_provider_vtable,
        .impl = binding,
        .shutdown_options =
            {
                .shutdown_callback = s_credentials_provider_shutdown_complete,
                .shutdown_user_data = binding,
            },
    };

    binding->native = aws_credentials_provider_new_delegate(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;
error:
    Py_DECREF(capsule);
    return NULL;
}
