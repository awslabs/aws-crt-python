/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "s3_client.h"

#include "auth.h"
#include "http.h"
#include "io.h"

#include <aws/http/request_response.h>
#include <aws/io/file_utils.h>
#include <aws/io/stream.h>

static const char *s_capsule_name_s3_meta_request = "aws_s3_meta_request";

struct s3_meta_request_binding {
    struct aws_s3_meta_request *native;

    bool release_called;
    bool shutdown_called;

    /* Reference proxy to python self */
    PyObject *self_py;

    /**
     * FILE pointer. If set, it handles file operation from C land to reduce the cost
     * passing chunks from C into python
     **/
    FILE *file;
    /**
     * input stream for using FILE pointer as the input body of a put request, keep it alive until the meta request
     * finishes.
     */
    struct aws_input_stream *input_body;
    /* Shutdown callback, all resource cleaned up, reference cleared after invoke */
    PyObject *on_shutdown;
};

static void s_destroy_if_ready(struct s3_meta_request_binding *meta_request) {
    if (meta_request->native && (!meta_request->shutdown_called || !meta_request->release_called)) {
        /* native meta_request successfully created, but not ready to clean up yet */
        return;
    }
    /* in case native never existed and shutdown never happened */
    Py_XDECREF(meta_request->on_shutdown);
    aws_mem_release(aws_py_get_allocator(), meta_request);
}

static void s_s3_meta_request_release(struct s3_meta_request_binding *meta_request) {
    AWS_FATAL_ASSERT(!meta_request->release_called);

    aws_s3_meta_request_release(meta_request->native);

    meta_request->release_called = true;

    s_destroy_if_ready(meta_request);
}

static int s_get_py_headers(const struct aws_http_headers *headers, PyObject *header_py) {
    /* Not take the reference of header_py, caller is the one holding the reference. */
    size_t num_headers = aws_http_headers_count(headers);

    for (size_t i = 0; i < num_headers; i++) {
        struct aws_http_header header;
        AWS_ZERO_STRUCT(header);
        if (aws_http_headers_get_index(headers, i, &header)) {
            goto error;
        }
        const char *name_str = (const char *)header.name.ptr;
        size_t name_len = header.name.len;
        const char *value_str = (const char *)header.value.ptr;
        size_t value_len = header.value.len;
        PyObject *tuple = Py_BuildValue("(s#s#)", name_str, name_len, value_str, value_len);
        if (!tuple) {
            goto error;
        }
        PyList_SET_ITEM(header_py, i, tuple); /* steals reference to tuple */
    }
    return AWS_OP_SUCCESS;
error:
    return AWS_OP_ERR;
}

static void s_s3_request_on_headers(
    struct aws_s3_meta_request *meta_request,
    const struct aws_http_headers *headers,
    int response_status,
    void *user_data) {
    (void)meta_request;
    struct s3_meta_request_binding *request_binding = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    size_t num_headers = aws_http_headers_count(headers);
    /* Build up a list of (name,value) tuples,
     * extracting values from buffer of [name,value,name,value,...] null-terminated strings */
    PyObject *header_list = PyList_New(num_headers);
    if (!header_list) {
        PyErr_WriteUnraisable(request_binding->self_py);
        goto done;
    }
    if (s_get_py_headers(headers, header_list)) {
        PyErr_WriteUnraisable(request_binding->self_py);
        goto done;
    }

    /* Deliver the built up list of (name,value) tuples */
    PyObject *result =
        PyObject_CallMethod(request_binding->self_py, "_on_headers", "(iO)", response_status, header_list);
    if (!result) {
        PyErr_WriteUnraisable(request_binding->self_py);
        goto done;
    }
    Py_DECREF(result);
done:
    Py_XDECREF(header_list);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

static void s_s3_request_on_body(
    struct aws_s3_meta_request *meta_request,
    const struct aws_byte_cursor *body,
    uint64_t range_start,
    void *user_data) {
    (void)meta_request;
    struct s3_meta_request_binding *request_binding = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    if (request_binding->file) {
        fwrite((void *)body->ptr, body->len, 1, request_binding->file);
        goto done;
    }
    PyObject *result = PyObject_CallMethod(
        request_binding->self_py, "_on_body", "(y#K)", (const char *)(body->ptr), (Py_ssize_t)body->len, range_start);

    if (!result) {
        PyErr_WriteUnraisable(request_binding->self_py);
        goto done;
    }
    Py_DECREF(result);

done:
    result = PyObject_CallMethod(request_binding->self_py, "_on_progress", "(K)", body->len);
    if (!result) {
        PyErr_WriteUnraisable(request_binding->self_py);
    } else {
        Py_DECREF(result);
    }
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

/* If the request has not finished, it will keep the request alive, until the finish callback invoked. So, we don't need
 * to clean anything from this call */
static void s_s3_request_on_finish(
    struct aws_s3_meta_request *meta_request,
    const struct aws_s3_meta_request_result *meta_request_result,
    void *user_data) {
    (void)meta_request;
    struct s3_meta_request_binding *request_binding = user_data;
    if (request_binding->input_body) {
        aws_input_stream_destroy(request_binding->input_body);
    }

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    PyObject *result;
    PyObject *header_list = Py_None;
    if (meta_request_result->error_code) {
        /* Get the header and body of the error */
        header_list = PyList_New(aws_http_headers_count(meta_request_result->error_response_headers));
        if (!header_list) {
            PyErr_WriteUnraisable(request_binding->self_py);
            Py_XDECREF(header_list);
            goto done;
        }
        if (s_get_py_headers(meta_request_result->error_response_headers, header_list)) {
            PyErr_WriteUnraisable(request_binding->self_py);
            Py_XDECREF(header_list);
            goto done;
        }
        struct aws_byte_buf *error_body = meta_request_result->error_response_body;
        result = PyObject_CallMethod(
            request_binding->self_py,
            "_on_finish",
            "(iOy#)",
            meta_request_result->error_code,
            header_list,
            (const char *)(error_body->buffer),
            (Py_ssize_t)error_body->len);
        Py_XDECREF(header_list);
    } else {
        result = PyObject_CallMethod(
            request_binding->self_py, "_on_finish", "(iOy#)", meta_request_result->error_code, header_list, NULL, 0);
    }
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(request_binding->self_py);
    }
done:
    Py_CLEAR(request_binding->self_py);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

/* Invoked when the python object get cleaned up */
static void s_s3_meta_request_capsule_destructor(PyObject *capsule) {
    struct s3_meta_request_binding *meta_request = PyCapsule_GetPointer(capsule, s_capsule_name_s3_meta_request);
    Py_XDECREF(meta_request->self_py);
    if (meta_request->file) {
        fclose(meta_request->file);
    }
    s_s3_meta_request_release(meta_request);
}

/* Callback from C land, invoked when the underlying shutdown process finished */
static void s_s3_request_on_shutdown(void *user_data) {
    struct s3_meta_request_binding *request_binding = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    request_binding->shutdown_called = true;

    bool destroy_after_shutdown = request_binding->release_called;

    /* Invoke on_shutdown, then clear our reference to it */
    PyObject *result = PyObject_CallFunction(request_binding->on_shutdown, NULL);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    Py_CLEAR(request_binding->on_shutdown);

    if (destroy_after_shutdown) {
        aws_mem_release(aws_py_get_allocator(), request_binding);
    }

    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

/* TODO: probably should put the input stream to somewhere else, but to keep it simple and timely manner. */
/*
 * file-based python input stream for reporting the progress
 */
struct aws_input_py_stream_file_impl {
    FILE *file;
    bool close_on_clean_up;
    struct s3_meta_request_binding *binding;
};

static int s_aws_input_stream_file_read(struct aws_input_stream *stream, struct aws_byte_buf *dest) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;

    size_t max_read = dest->capacity - dest->len;
    size_t actually_read = fread(dest->buffer + dest->len, 1, max_read, impl->file);
    if (actually_read == 0) {
        if (ferror(impl->file)) {
            return aws_raise_error(AWS_IO_STREAM_READ_FAILED);
        }
    }

    dest->len += actually_read;
    /*************** GIL ACQUIRE ***************/
    struct s3_meta_request_binding *request_binding = impl->binding;
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_SUCCESS; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    PyObject *result = PyObject_CallMethod(request_binding->self_py, "_on_progress", "(K)", dest->len);
    if (!result) {
        PyErr_WriteUnraisable(request_binding->self_py);
    } else {
        Py_DECREF(result);
    }
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
    return AWS_OP_SUCCESS;
}
static int s_aws_input_stream_file_seek(
    struct aws_input_stream *stream,
    aws_off_t offset,
    enum aws_stream_seek_basis basis) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;

    int whence = (basis == AWS_SSB_BEGIN) ? SEEK_SET : SEEK_END;
    if (aws_fseek(impl->file, offset, whence)) {
        return AWS_OP_ERR;
    }

    return AWS_OP_SUCCESS;
}

static int s_aws_input_stream_file_get_status(struct aws_input_stream *stream, struct aws_stream_status *status) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;

    status->is_end_of_stream = feof(impl->file) != 0;
    status->is_valid = ferror(impl->file) == 0;

    return AWS_OP_SUCCESS;
}

static int s_aws_input_stream_file_get_length(struct aws_input_stream *stream, int64_t *length) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;

    return aws_file_get_length(impl->file, length);
}

static void s_aws_input_stream_file_destroy(struct aws_input_stream *stream) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;

    if (impl->close_on_clean_up && impl->file) {
        fclose(impl->file);
    }

    aws_mem_release(stream->allocator, stream);
}

static struct aws_input_stream_vtable s_aws_input_stream_file_vtable = {
    .seek = s_aws_input_stream_file_seek,
    .read = s_aws_input_stream_file_read,
    .get_status = s_aws_input_stream_file_get_status,
    .get_length = s_aws_input_stream_file_get_length,
    .destroy = s_aws_input_stream_file_destroy};

static struct aws_input_stream *s_input_stream_new_from_open_file(
    struct aws_allocator *allocator,
    FILE *file,
    struct s3_meta_request_binding *request_binding) {
    struct aws_input_stream *input_stream = NULL;
    struct aws_input_py_stream_file_impl *impl = NULL;

    aws_mem_acquire_many(
        allocator,
        2,
        &input_stream,
        sizeof(struct aws_input_stream),
        &impl,
        sizeof(struct aws_input_py_stream_file_impl));

    if (!input_stream) {
        return NULL;
    }
    AWS_ZERO_STRUCT(*input_stream);
    AWS_ZERO_STRUCT(*impl);

    input_stream->allocator = allocator;
    input_stream->vtable = &s_aws_input_stream_file_vtable;
    input_stream->impl = impl;

    impl->file = file;
    impl->close_on_clean_up = false;
    impl->binding = request_binding;

    return input_stream;
}

PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *py_s3_request = NULL;
    PyObject *s3_client_py = NULL;
    PyObject *http_request_py = NULL;
    int type;
    PyObject *credential_provider_py = NULL;
    const char *file_path;
    Py_ssize_t file_path_len;
    const char *region;
    Py_ssize_t region_len;
    PyObject *on_shutdown_py = NULL;
    if (!PyArg_ParseTuple(
            args,
            "OOOiOz#s#O",
            &py_s3_request,
            &s3_client_py,
            &http_request_py,
            &type,
            &credential_provider_py,
            &file_path,
            &file_path_len,
            &region,
            &region_len,
            &on_shutdown_py)) {
        return NULL;
    }
    struct aws_s3_client *s3_client = aws_py_get_s3_client(s3_client_py);
    if (!s3_client) {
        return NULL;
    }

    struct aws_http_message *http_request = aws_py_get_http_message(http_request_py);
    if (!http_request) {
        return NULL;
    }

    struct aws_credentials_provider *credential_provider = NULL;
    if (credential_provider_py != Py_None) {
        credential_provider = aws_py_get_credentials_provider(credential_provider_py);
        if (!credential_provider) {
            return NULL;
        }
    }

    struct aws_signing_config_aws signing_config;
    AWS_ZERO_STRUCT(signing_config);
    if (credential_provider) {
        struct aws_byte_cursor region_cursor = aws_byte_cursor_from_array((const uint8_t *)region, region_len);
        aws_s3_init_default_signing_config(&signing_config, region_cursor, credential_provider);
    }

    struct s3_meta_request_binding *meta_request = aws_mem_calloc(allocator, 1, sizeof(struct s3_meta_request_binding));
    if (!meta_request) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur */

    PyObject *capsule =
        PyCapsule_New(meta_request, s_capsule_name_s3_meta_request, s_s3_meta_request_capsule_destructor);
    if (!capsule) {
        aws_mem_release(allocator, meta_request);
        return NULL;
    }

    meta_request->on_shutdown = on_shutdown_py;
    Py_INCREF(meta_request->on_shutdown);

    meta_request->self_py = py_s3_request;
    Py_INCREF(meta_request->self_py);

    if (file_path) {
        meta_request->file = fopen(file_path, type == AWS_S3_META_REQUEST_TYPE_GET_OBJECT ? "wb+" : "rb+");
        if (type == AWS_S3_META_REQUEST_TYPE_PUT_OBJECT) {
            meta_request->input_body = s_input_stream_new_from_open_file(allocator, meta_request->file, meta_request);
            if (!meta_request->input_body) {
                PyErr_SetAwsLastError();
                goto error;
            }
            /* rewrite the input stream of the original request */
            aws_http_message_set_body_stream(http_request, meta_request->input_body);
        }
    }

    struct aws_s3_meta_request_options s3_meta_request_opt = {
        .type = type,
        .message = http_request,
        .signing_config = credential_provider ? &signing_config : NULL,
        .headers_callback = s_s3_request_on_headers,
        .body_callback = s_s3_request_on_body,
        .finish_callback = s_s3_request_on_finish,
        .shutdown_callback = s_s3_request_on_shutdown,
        .user_data = meta_request,
    };

    meta_request->native = aws_s3_client_make_meta_request(s3_client, &s3_meta_request_opt);
    if (meta_request->native == NULL) {
        PyErr_SetAwsLastError();
        goto error;
    }

    return capsule;

error:
    Py_DECREF(capsule);
    return NULL;
}
