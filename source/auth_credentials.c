/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */

#include "auth.h"

#include "http.h"
#include "io.h"

#include <aws/auth/credentials.h>
#include <aws/common/string.h>
#include <aws/http/proxy.h>
#include <aws/io/tls_channel_handler.h>

static const char *s_capsule_name_credentials = "aws_credentials";
static const char *s_capsule_name_credentials_provider = "aws_credentials_provider";

/* Credentials capsule contains raw aws_credentials struct. There is no intermediate binding struct. */

static void s_credentials_capsule_destructor(PyObject *capsule) {
    struct aws_credentials *credentials = PyCapsule_GetPointer(capsule, s_capsule_name_credentials);
    aws_credentials_release(credentials);
}

PyObject *aws_py_credentials_new_request_from_native(struct aws_credentials *credentials) {
    PyObject *capsule = PyCapsule_New(credentials, s_capsule_name_credentials, s_credentials_capsule_destructor);
    if (!capsule) {
        return NULL;
    }
    aws_credentials_acquire(credentials);
    return capsule;
}

PyObject *aws_py_credentials_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_byte_cursor access_key_id;
    struct aws_byte_cursor secret_access_key;
    struct aws_byte_cursor session_token; /* session_token is optional */
    uint64_t expiration_timestamp_sec;
    if (!PyArg_ParseTuple(
            args,
            "s#s#z#K",
            &access_key_id.ptr,
            &access_key_id.len,
            &secret_access_key.ptr,
            &secret_access_key.len,
            &session_token.ptr,
            &session_token.len,
            &expiration_timestamp_sec)) {
        return NULL;
    }

    struct aws_credentials *credentials = aws_credentials_new(
        aws_py_get_allocator(), access_key_id, secret_access_key, session_token, expiration_timestamp_sec);
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

PyObject *aws_py_credentials_expiration_timestamp_seconds(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) {
        return NULL;
    }

    const struct aws_credentials *credentials = PyCapsule_GetPointer(capsule, s_capsule_name_credentials);
    if (!credentials) {
        return NULL;
    }

    uint64_t timestamp = aws_credentials_get_expiration_timepoint_seconds(credentials);
    return PyLong_FromUnsignedLongLong(timestamp);
}

/**
 * Binds a Python CredentialsProvider to a native aws_credentials_provider.
 */
struct credentials_provider_binding {
    struct aws_credentials_provider *native;

    /* Python get_credentials() callable.
     * Only used by "delegate" provider type */
    PyObject *py_delegate;
};

/* Finally clean up binding (after capsule destructor runs and credentials provider shutdown completes) */
static void s_credentials_provider_binding_clean_up(struct credentials_provider_binding *binding) {
    Py_XDECREF(binding->py_delegate);

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
        "AwsCredentialsProvider",
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
    size_t provider_count = (size_t)PySequence_Size(providers_pyseq);
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
        PyObject *provider_py = PySequence_GetItem(providers_pyseq, i); /* new reference */
        providers_carray[i] = aws_py_get_credentials_provider(provider_py);
        Py_XDECREF(provider_py);
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

static int s_credentials_provider_delegate_get_credentials(
    void *delegate_user_data,
    aws_on_get_credentials_callback_fn callback,
    void *callback_user_data) {

    struct credentials_provider_binding *binding = delegate_user_data;

    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        /* Python has shut down. Nothing matters anymore, but don't crash */
        return aws_raise_error(AWS_ERROR_INVALID_STATE);
    }

    struct aws_credentials *native_credentials = NULL;

    PyObject *py_result = PyObject_CallFunction(binding->py_delegate, "()");
    if (!py_result) {
        AWS_LOGF_ERROR(
            AWS_LS_AUTH_CREDENTIALS_PROVIDER,
            "(id=%p) Exception in get_credentials() delegate callback",
            (void *)binding->native);

        PyErr_WriteUnraisable(binding->py_delegate);
        goto done;
    }

    /* Expect py_result to be AwsCredentials (which wraps native aws_credentials). */
    native_credentials = aws_py_get_credentials(py_result);
    if (!native_credentials) {
        AWS_LOGF_ERROR(
            AWS_LS_AUTH_CREDENTIALS_PROVIDER,
            "(id=%p) get_credentials() delegate callback failed to return AwsCredentials",
            (void *)binding->native);

        PyErr_WriteUnraisable(binding->py_delegate);
        goto done;
    }

    /* Keep native aws_credentials alive until we pass them to callback. */
    aws_credentials_acquire(native_credentials);

done:
    /* Decref the python AwsCredentials (or whatever else was returned) before releasing the GIL */
    Py_XDECREF(py_result);

    PyGILState_Release(state);

    if (!native_credentials) {
        return aws_raise_error(AWS_AUTH_CREDENTIALS_PROVIDER_DELEGATE_FAILURE);
    }

    callback(native_credentials, AWS_ERROR_SUCCESS, callback_user_data);
    aws_credentials_release(native_credentials);
    return AWS_OP_SUCCESS;
}

PyObject *aws_py_credentials_provider_new_delegate(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *py_delegate;

    if (!PyArg_ParseTuple(args, "O", &py_delegate)) {
        return NULL;
    }

    struct credentials_provider_binding *binding;
    PyObject *capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        return NULL;
    }

    binding->py_delegate = py_delegate;
    Py_INCREF(py_delegate);

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    struct aws_credentials_provider_delegate_options options = {
        .get_credentials = s_credentials_provider_delegate_get_credentials,
        .delegate_user_data = binding,
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

PyObject *aws_py_credentials_provider_new_cognito(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_byte_cursor endpoint_cursor;
    AWS_ZERO_STRUCT(endpoint_cursor);
    struct aws_byte_cursor identity_cursor;
    AWS_ZERO_STRUCT(identity_cursor);
    PyObject *logins_list_py = NULL;
    struct aws_byte_cursor custom_role_arn_cursor;
    AWS_ZERO_STRUCT(custom_role_arn_cursor);
    PyObject *tls_context_py = NULL;
    PyObject *client_bootstrap_py = NULL;
    PyObject *http_proxy_options_py = NULL;

    if (!PyArg_ParseTuple(
            args,
            "s#s#OOOz#O",
            &endpoint_cursor.ptr,
            &endpoint_cursor.len,
            &identity_cursor.ptr,
            &identity_cursor.len,
            &tls_context_py,
            &client_bootstrap_py,
            &logins_list_py,
            &custom_role_arn_cursor.ptr,
            &custom_role_arn_cursor.len,
            &http_proxy_options_py)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(client_bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct aws_tls_ctx *tls_context = aws_py_get_tls_ctx(tls_context_py);
    if (!tls_context) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */
    bool success = false;
    PyObject *logins_pyseq = NULL;
    struct aws_cognito_identity_provider_token_pair *logins_carray = NULL;
    PyObject *capsule = NULL;
    size_t logins_count = 0;

    if (logins_list_py != Py_None) {
        logins_pyseq = PySequence_Fast(logins_list_py, "Expected sequence of login token tuples");
        if (!logins_pyseq) {
            goto done;
        }

        logins_count = (size_t)PySequence_Size(logins_pyseq);
        if (logins_count > 0) {

            logins_carray =
                aws_mem_calloc(allocator, logins_count, sizeof(struct aws_cognito_identity_provider_token_pair));
            if (!logins_carray) {
                PyErr_SetAwsLastError();
                goto done;
            }

            for (size_t i = 0; i < logins_count; ++i) {
                PyObject *login_tuple_py = PySequence_GetItem(logins_pyseq, i); /* New reference */
                struct aws_cognito_identity_provider_token_pair *login_entry = &logins_carray[i];
                AWS_ZERO_STRUCT(*login_entry);

                if (!PyArg_ParseTuple(
                        login_tuple_py,
                        "s#s#",
                        &login_entry->identity_provider_name.ptr,
                        &login_entry->identity_provider_name.len,
                        &login_entry->identity_provider_token.ptr,
                        &login_entry->identity_provider_token.len)) {
                    PyErr_Format(
                        PyExc_TypeError,
                        "cognito credentials provider: logins[%zu] is invalid, should be type (str, str)",
                        i);
                    Py_XDECREF(login_tuple_py);
                    goto done;
                }
                Py_XDECREF(login_tuple_py);
            }
        }
    }

    struct aws_http_proxy_options http_proxy_options_storage;
    struct aws_http_proxy_options *http_proxy_options = NULL;
    if (http_proxy_options_py != Py_None) {
        http_proxy_options = &http_proxy_options_storage;
        if (!aws_py_http_proxy_options_init(http_proxy_options, http_proxy_options_py)) {
            goto done;
        }
    }

    struct credentials_provider_binding *binding = NULL;
    capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        goto done;
    }

    struct aws_credentials_provider_cognito_options options = {
        .endpoint = endpoint_cursor,
        .identity = identity_cursor,
        .shutdown_options =
            {
                .shutdown_callback = s_credentials_provider_shutdown_complete,
                .shutdown_user_data = binding,
            },
        .tls_ctx = tls_context,
        .bootstrap = bootstrap,
        .http_proxy_options = http_proxy_options,
    };

    if (logins_count > 0) {
        options.login_count = logins_count;
        options.logins = logins_carray;
    }

    if (custom_role_arn_cursor.ptr != NULL) {
        options.custom_role_arn = &custom_role_arn_cursor;
    }

    binding->native = aws_credentials_provider_new_cognito(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto done;
    }

    success = true;

done:
    Py_XDECREF(logins_pyseq);
    aws_mem_release(allocator, logins_carray);

    if (success) {
        return capsule;
    }

    Py_XDECREF(capsule);
    return NULL;
}

PyObject *aws_py_credentials_provider_new_x509(PyObject *self, PyObject *args) {
    (void)self;
    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_byte_cursor endpoint_cursor;
    AWS_ZERO_STRUCT(endpoint_cursor);
    struct aws_byte_cursor thing_name_cursor;
    AWS_ZERO_STRUCT(thing_name_cursor);
    struct aws_byte_cursor role_alias_cursor;
    AWS_ZERO_STRUCT(role_alias_cursor);
    PyObject *tls_context_py = NULL;
    PyObject *client_bootstrap_py = NULL;
    PyObject *http_proxy_options_py = NULL;
    struct aws_tls_connection_options tls_connection_options;
    AWS_ZERO_STRUCT(tls_connection_options);

    if (!PyArg_ParseTuple(
            args,
            "s#s#s#OOO",
            &endpoint_cursor.ptr,   /* s */
            &endpoint_cursor.len,   /* # */
            &thing_name_cursor.ptr, /* s */
            &thing_name_cursor.len, /* # */
            &role_alias_cursor.ptr, /* s */
            &role_alias_cursor.len, /* # */
            &tls_context_py,        /* O */
            &client_bootstrap_py,   /* O */
            &http_proxy_options_py /* O */)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(client_bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct aws_tls_ctx *tls_context = aws_py_get_tls_ctx(tls_context_py);
    if (!tls_context) {
        return NULL;
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */
    PyObject *capsule = NULL;
    bool success = false;
    aws_tls_connection_options_init_from_ctx(&tls_connection_options, tls_context);

    struct aws_http_proxy_options http_proxy_options_storage;
    struct aws_http_proxy_options *http_proxy_options = NULL;
    if (http_proxy_options_py != Py_None) {
        http_proxy_options = &http_proxy_options_storage;
        if (!aws_py_http_proxy_options_init(http_proxy_options, http_proxy_options_py)) {
            goto done;
        }
    }

    struct credentials_provider_binding *binding = NULL;
    capsule = s_new_credentials_provider_binding_and_capsule(&binding);
    if (!capsule) {
        goto done;
    }

    struct aws_credentials_provider_x509_options options = {
        .endpoint = endpoint_cursor,
        .thing_name = thing_name_cursor,
        .role_alias = role_alias_cursor,
        .shutdown_options =
            {
                .shutdown_callback = s_credentials_provider_shutdown_complete,
                .shutdown_user_data = binding,
            },
        .tls_connection_options = &tls_connection_options,
        .bootstrap = bootstrap,
        .proxy_options = http_proxy_options,
    };

    binding->native = aws_credentials_provider_new_x509(allocator, &options);
    if (!binding->native) {
        PyErr_SetAwsLastError();
        goto done;
    }
    success = true;

done:
    aws_tls_connection_options_clean_up(&tls_connection_options);
    if (success) {
        return capsule;
    }
    Py_XDECREF(capsule);
    return NULL;
}
