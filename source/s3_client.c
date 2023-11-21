/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "s3.h"

#include "auth.h"
#include "io.h"
#include <aws/common/cross_process_lock.h>
#include <aws/s3/s3_client.h>

static const char *s_capsule_name_s3_client = "aws_s3_client";
static const char *s_capsule_name_s3_instance_lock = "aws_cross_process_lock";

PyObject *aws_py_s3_get_ec2_instance_type(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    const struct aws_s3_platform_info *platform_info = aws_s3_get_current_platform_info();

    if (platform_info->instance_type.len) {
        PyObject *ret_value = PyUnicode_FromAwsByteCursor(&platform_info->instance_type);
        return ret_value;
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_s3_is_crt_s3_optimized_for_system(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    const struct aws_s3_platform_info *platform_info = aws_s3_get_current_platform_info();

    if (platform_info->has_recommended_configuration) {
        Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}

PyObject *aws_py_s3_get_recommended_throughput_target_gbps(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    const struct aws_s3_platform_info *platform_info = aws_s3_get_current_platform_info();

    return PyFloat_FromDouble(platform_info->max_throughput_gbps);
}

PyObject *aws_py_s3_get_optimized_platforms(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    bool success = false;
    struct aws_array_list platform_list = aws_s3_get_platforms_with_recommended_config();

    size_t list_length = aws_array_list_length(&platform_list);

    PyObject *py_list = PyList_New(list_length);
    if (!py_list) {
        goto clean_up;
    }

    for (size_t i = 0; i < list_length; ++i) {
        struct aws_byte_cursor cursor;
        if (aws_array_list_get_at(&platform_list, &cursor, i) == AWS_OP_SUCCESS) {
            PyObject *platform_str = PyUnicode_FromAwsByteCursor(&cursor);
            if (!platform_str) {
                Py_DECREF(py_list);
                goto clean_up;
            }
            PyList_SetItem(py_list, i, platform_str); /* Steals a Reference */
        }
    }
    success = true;

clean_up:
    aws_array_list_clean_up(&platform_list);
    return success ? py_list : NULL;
}

struct cross_process_lock_binding {
    struct aws_cross_process_lock *lock;
    struct aws_string *name;
};

/* Invoked when the python object gets cleaned up */
static void s_s3_cross_process_lock_destructor(PyObject *capsule) {
    struct cross_process_lock_binding *lock_binding = PyCapsule_GetPointer(capsule, s_capsule_name_s3_instance_lock);

    if (lock_binding->lock) {
        aws_cross_process_lock_release(lock_binding->lock);
        lock_binding->lock = NULL;
    }

    if (lock_binding->name) {
        aws_string_destroy(lock_binding->name);
    }

    aws_mem_release(aws_py_get_allocator(), lock_binding);
}

PyObject *aws_py_s3_cross_process_lock_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    struct aws_byte_cursor lock_name; /* s# */

    if (!PyArg_ParseTuple(args, "s#", &lock_name.ptr, &lock_name.len)) {
        return NULL;
    }

    struct cross_process_lock_binding *binding =
        aws_mem_calloc(allocator, 1, sizeof(struct cross_process_lock_binding));
    binding->name = aws_string_new_from_cursor(allocator, &lock_name);

    PyObject *capsule = PyCapsule_New(binding, s_capsule_name_s3_instance_lock, s_s3_cross_process_lock_destructor);
    if (!capsule) {
        aws_string_destroy(binding->name);
        aws_mem_release(allocator, binding);
        return PyErr_AwsLastError();
    }

    return capsule;
}

PyObject *aws_py_s3_cross_process_lock_acquire(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *lock_capsule; /* O */

    if (!PyArg_ParseTuple(args, "O", &lock_capsule)) {
        return NULL;
    }

    struct cross_process_lock_binding *lock_binding =
        PyCapsule_GetPointer(lock_capsule, s_capsule_name_s3_instance_lock);
    if (!lock_binding) {
        return NULL;
    }

    if (!lock_binding->lock) {
        struct aws_cross_process_lock *lock =
            aws_cross_process_lock_try_acquire(allocator, aws_byte_cursor_from_string(lock_binding->name));

        if (!lock) {
            return PyErr_AwsLastError();
        }
        lock_binding->lock = lock;
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_s3_cross_process_lock_release(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *lock_capsule; /* O */

    if (!PyArg_ParseTuple(args, "O", &lock_capsule)) {
        return NULL;
    }

    struct cross_process_lock_binding *lock_binding =
        PyCapsule_GetPointer(lock_capsule, s_capsule_name_s3_instance_lock);
    if (!lock_binding) {
        return NULL;
    }

    if (lock_binding->lock) {
        aws_cross_process_lock_release(lock_binding->lock);
        lock_binding->lock = NULL;
    }

    Py_RETURN_NONE;
}

struct s3_client_binding {
    struct aws_s3_client *native;

    /* Shutdown callback, reference cleared after invoking callback */
    PyObject *on_shutdown;
    /* Reference to python object that reference to other related python object to keep it alive */
    PyObject *py_core;
};

static void s_destroy(struct s3_client_binding *client) {
    Py_XDECREF(client->on_shutdown);
    Py_XDECREF(client->py_core);
    aws_mem_release(aws_py_get_allocator(), client);
}

/* Invoked when the python object get cleaned up */
static void s_s3_client_capsule_destructor(PyObject *capsule) {
    struct s3_client_binding *client = PyCapsule_GetPointer(capsule, s_capsule_name_s3_client);

    if (client->native) {
        aws_s3_client_release(client->native);
    } else {
        /* we hit this branch if things failed part way through setting up the binding,
         * before the native aws_s3_meta_request could be created. */
        s_destroy(client);
    }
}

/* Callback from C land, invoked when the underlying shutdown process finished */
static void s_s3_client_shutdown(void *user_data) {
    struct s3_client_binding *client = user_data;

    /* Lock for python */
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Invoke on_shutdown, then clear our reference to it */
    PyObject *result = PyObject_CallFunction(client->on_shutdown, NULL);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }

    s_destroy(client);

    PyGILState_Release(state);
}

struct aws_s3_client *aws_py_get_s3_client(PyObject *client) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(client, s_capsule_name_s3_client, "S3Client", s3_client_binding);
}

PyObject *aws_py_s3_client_new(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *bootstrap_py;              /* O */
    PyObject *signing_config_py;         /* O */
    PyObject *credential_provider_py;    /* O */
    PyObject *tls_options_py;            /* O */
    PyObject *on_shutdown_py;            /* O */
    struct aws_byte_cursor region;       /* s# */
    int tls_mode;                        /* i */
    uint64_t part_size;                  /* K */
    uint64_t multipart_upload_threshold; /* K */
    double throughput_target_gbps;       /* d */
    uint64_t mem_limit;                  /* K */
    PyObject *py_core;                   /* O */
    if (!PyArg_ParseTuple(
            args,
            "OOOOOs#iKKdKO",
            &bootstrap_py,
            &signing_config_py,
            &credential_provider_py,
            &tls_options_py,
            &on_shutdown_py,
            &region.ptr,
            &region.len,
            &tls_mode,
            &part_size,
            &multipart_upload_threshold,
            &throughput_target_gbps,
            &mem_limit,
            &py_core)) {
        return NULL;
    }

    struct aws_client_bootstrap *bootstrap = aws_py_get_client_bootstrap(bootstrap_py);
    if (!bootstrap) {
        return NULL;
    }

    struct aws_credentials_provider *credential_provider = NULL;
    if (credential_provider_py != Py_None) {
        credential_provider = aws_py_get_credentials_provider(credential_provider_py);
        if (!credential_provider) {
            return NULL;
        }
    }
    struct aws_signing_config_aws *signing_config = NULL;
    if (signing_config_py != Py_None) {
        signing_config = aws_py_get_signing_config(signing_config_py);
        if (!signing_config) {
            return NULL;
        }
    }
    struct aws_signing_config_aws signing_config_from_credentials_provider;
    AWS_ZERO_STRUCT(signing_config_from_credentials_provider);

    if (credential_provider) {
        aws_s3_init_default_signing_config(&signing_config_from_credentials_provider, region, credential_provider);
        signing_config = &signing_config_from_credentials_provider;
    }

    struct aws_tls_connection_options *tls_options = NULL;
    if (tls_options_py != Py_None) {
        tls_options = aws_py_get_tls_connection_options(tls_options_py);
        if (!tls_options) {
            return NULL;
        }
    }

    struct s3_client_binding *s3_client = aws_mem_calloc(allocator, 1, sizeof(struct s3_client_binding));
    if (!s3_client) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur */

    PyObject *capsule = PyCapsule_New(s3_client, s_capsule_name_s3_client, s_s3_client_capsule_destructor);
    if (!capsule) {
        aws_mem_release(allocator, s3_client);
        return NULL;
    }

    s3_client->on_shutdown = on_shutdown_py;
    Py_INCREF(s3_client->on_shutdown);

    s3_client->py_core = py_core;
    Py_INCREF(s3_client->py_core);

    struct aws_s3_client_config s3_config = {
        .region = region,
        .client_bootstrap = bootstrap,
        .tls_mode = tls_mode,
        .signing_config = signing_config,
        .part_size = part_size,
        .memory_limit_in_bytes = mem_limit,
        .multipart_upload_threshold = multipart_upload_threshold,
        .tls_connection_options = tls_options,
        .throughput_target_gbps = throughput_target_gbps,
        .shutdown_callback = s_s3_client_shutdown,
        .shutdown_callback_user_data = s3_client,
    };

    s3_client->native = aws_s3_client_new(allocator, &s3_config);
    if (s3_client->native == NULL) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;

error:
    Py_DECREF(capsule);
    return NULL;
}
