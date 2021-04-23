/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "s3.h"

#include "auth.h"
#include "http.h"
#include "io.h"
#include <errno.h>

#include <aws/common/clock.h>
#include <aws/common/file.h>
#include <aws/http/request_response.h>
#include <aws/io/file_utils.h>
#include <aws/io/stream.h>
#include <aws/s3/s3_client.h>

static const char *s_capsule_name_s3_meta_request = "aws_s3_meta_request";

struct s3_meta_request_binding {
    struct aws_s3_meta_request *native;

    /* Reference to python object that reference to other related python object to keep it alive */
    PyObject *py_core;

    /**
     * file path if set, it handles file operation from C land to reduce the cost
     * passing chunks from C into python. One for recv/writing, the other for send/reading
     **/
    FILE *recv_file;
    /**
     * input stream for using FILE pointer as the input body of a put request, keep it alive until the meta request
     * finishes.
     */
    struct aws_input_stream *input_body;

    struct aws_http_message *copied_message;

    /* Batch up the transferred size in one sec. */
    uint64_t size_transferred;
    /* The time stamp when the progress reported */
    uint64_t last_sampled_time;
};

struct aws_s3_meta_request *aws_py_get_s3_meta_request(PyObject *meta_request) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        meta_request, s_capsule_name_s3_meta_request, "S3Request", s3_meta_request_binding);
}

static void s_destroy(struct s3_meta_request_binding *meta_request) {
    if (meta_request->input_body) {
        aws_input_stream_destroy(meta_request->input_body);
    }

    if (meta_request->copied_message) {
        aws_http_message_release(meta_request->copied_message);
    }
    Py_XDECREF(meta_request->py_core);
    aws_mem_release(aws_py_get_allocator(), meta_request);
}

static PyObject *s_get_py_headers(const struct aws_http_headers *headers) {
    size_t num_headers = aws_http_headers_count(headers);
    PyObject *header_list = PyList_New(num_headers);
    if (!header_list) {
        return NULL;
    }
    for (size_t i = 0; i < num_headers; i++) {
        struct aws_http_header header;
        AWS_ZERO_STRUCT(header);
        aws_http_headers_get_index(headers, i, &header);
        const char *name_str = (const char *)header.name.ptr;
        size_t name_len = header.name.len;
        const char *value_str = (const char *)header.value.ptr;
        size_t value_len = header.value.len;
        PyObject *tuple = Py_BuildValue("(s#s#)", name_str, name_len, value_str, value_len);
        if (!tuple) {
            goto error;
        }
        PyList_SET_ITEM(header_list, i, tuple); /* steals reference to tuple */
    }
    return header_list;
error:
    Py_XDECREF(header_list);
    return NULL;
}

static int s_s3_request_on_headers(
    struct aws_s3_meta_request *meta_request,
    const struct aws_http_headers *headers,
    int response_status,
    void *user_data) {
    (void)meta_request;
    struct s3_meta_request_binding *request_binding = user_data;

    /*************** GIL ACQUIRE ***************/
    bool error = true;
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Build up a list of (name,value) tuples */
    PyObject *header_list = s_get_py_headers(headers);
    if (!header_list) {
        PyErr_WriteUnraisable(request_binding->py_core);
        goto done;
    }

    /* Deliver the built up list of (name,value) tuples */
    PyObject *result =
        PyObject_CallMethod(request_binding->py_core, "_on_headers", "(iO)", response_status, header_list);
    if (!result) {
        PyErr_WriteUnraisable(request_binding->py_core);
        goto done;
    }
    Py_DECREF(result);
    error = false;
done:
    Py_XDECREF(header_list);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
    if (error) {
        return aws_raise_error(AWS_ERROR_CRT_CALLBACK_EXCEPTION);
    } else {
        return AWS_OP_SUCCESS;
    }
}

static int s_record_progress(struct s3_meta_request_binding *request_binding, uint64_t length, bool *report_progress) {
    if (aws_add_u64_checked(request_binding->size_transferred, length, &request_binding->size_transferred)) {
        /* Wow */
        return AWS_OP_ERR;
    }
    uint64_t now;
    if (aws_high_res_clock_get_ticks(&now)) {
        return AWS_OP_ERR;
    }
    uint64_t nanos = 0;
    if (aws_sub_u64_checked(now, request_binding->last_sampled_time, &nanos)) {
        return AWS_OP_ERR;
    }
    uint64_t sec = aws_timestamp_convert(nanos, AWS_TIMESTAMP_NANOS, AWS_TIMESTAMP_SECS, NULL);
    *report_progress = (sec >= 1);
    if (*report_progress) {
        request_binding->last_sampled_time = now;
    }
    return AWS_OP_SUCCESS;
}

static int s_s3_request_on_body(
    struct aws_s3_meta_request *meta_request,
    const struct aws_byte_cursor *body,
    uint64_t range_start,
    void *user_data) {
    (void)meta_request;
    struct s3_meta_request_binding *request_binding = user_data;

    bool report_progress;
    if (s_record_progress(request_binding, (uint64_t)body->len, &report_progress)) {
        return AWS_OP_ERR;
    }
    if (request_binding->recv_file) {
        /* The callback will be invoked with the right order, so we don't need to seek first. */
        if (fwrite((void *)body->ptr, body->len, 1, request_binding->recv_file) < 1) {
            return aws_translate_and_raise_io_error(errno);
        }
        if (!report_progress) {
            return AWS_OP_SUCCESS;
        }
    }
    bool error = true;
    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    PyObject *result = NULL;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    if (!request_binding->recv_file) {
        result = PyObject_CallMethod(
            request_binding->py_core,
            "_on_body",
            "(y#K)",
            (const char *)(body->ptr),
            (Py_ssize_t)body->len,
            range_start);

        if (!result) {
            PyErr_WriteUnraisable(request_binding->py_core);
            goto done;
        }
        Py_DECREF(result);
    }
    if (report_progress) {
        /* Hold the GIL before enterring here */
        result =
            PyObject_CallMethod(request_binding->py_core, "_on_progress", "(K)", request_binding->size_transferred);
        if (!result) {
            PyErr_WriteUnraisable(request_binding->py_core);
        } else {
            Py_DECREF(result);
        }
        request_binding->size_transferred = 0;
    }
    error = false;
done:
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
    if (error) {
        return aws_raise_error(AWS_ERROR_CRT_CALLBACK_EXCEPTION);
    } else {
        return AWS_OP_SUCCESS;
    }
}

static void s_s3_request_on_finish(
    struct aws_s3_meta_request *meta_request,
    const struct aws_s3_meta_request_result *meta_request_result,
    void *user_data) {
    (void)meta_request;
    struct s3_meta_request_binding *request_binding = user_data;

    if (request_binding->recv_file) {
        fclose(request_binding->recv_file);
        request_binding->recv_file = NULL;
    }
    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *header_list = NULL;
    PyObject *result = NULL;

    if (request_binding->input_body) {
        /* close the input file stream now, request has finished, we will not read from there anymore */
        aws_input_stream_destroy(request_binding->input_body);
        request_binding->input_body = NULL;
    }

    if (request_binding->size_transferred) {
        /* report the remaining progress */
        result =
            PyObject_CallMethod(request_binding->py_core, "_on_progress", "(K)", request_binding->size_transferred);
        if (!result) {
            PyErr_WriteUnraisable(request_binding->py_core);
        } else {
            Py_DECREF(result);
        }
        request_binding->size_transferred = 0;
    }
    struct aws_byte_buf error_body;
    AWS_ZERO_STRUCT(error_body);
    /* Get the header and body of the error */
    if (meta_request_result->error_response_headers) {
        header_list = s_get_py_headers(meta_request_result->error_response_headers);
        if (!header_list) {
            PyErr_WriteUnraisable(request_binding->py_core);
            goto done;
        }
    }
    if (meta_request_result->error_response_body) {
        error_body = *(meta_request_result->error_response_body);
    }
    result = PyObject_CallMethod(
        request_binding->py_core,
        "_on_finish",
        "(iOy#)",
        meta_request_result->error_code,
        header_list ? header_list : Py_None,
        (const char *)(error_body.buffer),
        (Py_ssize_t)error_body.len);

    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(request_binding->py_core);
    }
done:
    Py_XDECREF(header_list);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

/* Invoked when the python object get cleaned up */
static void s_s3_meta_request_capsule_destructor(PyObject *capsule) {
    struct s3_meta_request_binding *meta_request = PyCapsule_GetPointer(capsule, s_capsule_name_s3_meta_request);

    if (meta_request->recv_file) {
        fclose(meta_request->recv_file);
        meta_request->recv_file = NULL;
    }
    if (meta_request->native) {
        aws_s3_meta_request_release(meta_request->native);
    } else {
        /* we hit this branch if things failed part way through setting up the binding,
         * before the native aws_s3_meta_request could be created. */
        s_destroy(meta_request);
    }
}

/* Callback from C land, invoked when the underlying shutdown process finished */
static void s_s3_request_on_shutdown(void *user_data) {
    struct s3_meta_request_binding *request_binding = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    /* Deliver the built up list of (name,value) tuples */
    PyObject *result = PyObject_CallMethod(request_binding->py_core, "_on_shutdown", NULL);
    if (!result) {
        PyErr_WriteUnraisable(request_binding->py_core);
    }

    s_destroy(request_binding);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

/*
 * file-based python input stream for reporting the progress
 */
struct aws_input_py_stream_file_impl {
    struct aws_input_stream *actual_stream;
    struct s3_meta_request_binding *binding;
};

static int s_aws_input_stream_file_read(struct aws_input_stream *stream, struct aws_byte_buf *dest) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;
    size_t pre_len = dest->len;

    if (aws_input_stream_read(impl->actual_stream, dest)) {
        return AWS_OP_ERR;
    }

    size_t actually_read = 0;
    if (aws_sub_size_checked(dest->len, pre_len, &actually_read)) {
        return AWS_OP_ERR;
    }

    bool report_progress;
    struct s3_meta_request_binding *request_binding = impl->binding;
    if (s_record_progress(request_binding, (uint64_t)actually_read, &report_progress)) {
        return AWS_OP_ERR;
    }

    if (report_progress) {
        /*************** GIL ACQUIRE ***************/
        PyGILState_STATE state;
        if (aws_py_gilstate_ensure(&state)) {
            return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
        }
        PyObject *result =
            PyObject_CallMethod(request_binding->py_core, "_on_progress", "(K)", request_binding->size_transferred);
        if (result) {
            Py_DECREF(result);
        }
        request_binding->size_transferred = 0;
        PyGILState_Release(state);
        /*************** GIL RELEASE ***************/
        if (!result) {
            return aws_py_raise_error();
        }
    }
    return AWS_OP_SUCCESS;
}
static int s_aws_input_stream_file_seek(
    struct aws_input_stream *stream,
    aws_off_t offset,
    enum aws_stream_seek_basis basis) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;
    return aws_input_stream_seek(impl->actual_stream, offset, basis);
}

static int s_aws_input_stream_file_get_status(struct aws_input_stream *stream, struct aws_stream_status *status) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;
    return aws_input_stream_get_status(impl->actual_stream, status);
}

static int s_aws_input_stream_file_get_length(struct aws_input_stream *stream, int64_t *length) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;
    return aws_input_stream_get_length(impl->actual_stream, length);
}

static void s_aws_input_stream_file_destroy(struct aws_input_stream *stream) {
    struct aws_input_py_stream_file_impl *impl = stream->impl;

    aws_input_stream_destroy(impl->actual_stream);

    aws_mem_release(stream->allocator, stream);
}

static struct aws_input_stream_vtable s_aws_input_stream_file_vtable = {
    .seek = s_aws_input_stream_file_seek,
    .read = s_aws_input_stream_file_read,
    .get_status = s_aws_input_stream_file_get_status,
    .get_length = s_aws_input_stream_file_get_length,
    .destroy = s_aws_input_stream_file_destroy,
};

static struct aws_input_stream *s_input_stream_new_from_file(
    struct aws_allocator *allocator,
    const char *file_name,
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

    impl->actual_stream = aws_input_stream_new_from_file(allocator, file_name);
    if (!impl->actual_stream) {
        aws_mem_release(allocator, input_stream);
        return NULL;
    }
    impl->binding = request_binding;

    return input_stream;
}

/* Copy an existing HTTP message without body. */
struct aws_http_message *s_copy_http_message(struct aws_allocator *allocator, struct aws_http_message *base_message) {
    AWS_PRECONDITION(allocator);
    AWS_PRECONDITION(base_message);

    struct aws_http_message *message = aws_http_message_new_request(allocator);

    if (message == NULL) {
        return NULL;
    }

    struct aws_byte_cursor request_method;
    if (aws_http_message_get_request_method(base_message, &request_method)) {
        goto error_clean_up;
    }

    if (aws_http_message_set_request_method(message, request_method)) {
        goto error_clean_up;
    }

    struct aws_byte_cursor request_path;
    if (aws_http_message_get_request_path(base_message, &request_path)) {
        goto error_clean_up;
    }

    if (aws_http_message_set_request_path(message, request_path)) {
        goto error_clean_up;
    }

    size_t num_headers = aws_http_message_get_header_count(base_message);
    for (size_t header_index = 0; header_index < num_headers; ++header_index) {
        struct aws_http_header header;
        if (aws_http_message_get_header(base_message, &header, header_index)) {
            goto error_clean_up;
        }
        if (aws_http_message_add_header(message, header)) {
            goto error_clean_up;
        }
    }

    return message;

error_clean_up:

    if (message != NULL) {
        aws_http_message_release(message);
        message = NULL;
    }

    return NULL;
}

PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *py_s3_request = NULL;
    PyObject *s3_client_py = NULL;
    PyObject *http_request_py = NULL;
    int type;
    PyObject *credential_provider_py = NULL;
    const char *recv_filepath;
    const char *send_filepath;
    const char *region;
    Py_ssize_t region_len;
    PyObject *py_core = NULL;
    if (!PyArg_ParseTuple(
            args,
            "OOOiOzzs#O",
            &py_s3_request,
            &s3_client_py,
            &http_request_py,
            &type,
            &credential_provider_py,
            &recv_filepath,
            &send_filepath,
            &region,
            &region_len,
            &py_core)) {
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

    meta_request->py_core = py_core;
    Py_INCREF(meta_request->py_core);

    if (recv_filepath) {
        meta_request->recv_file = aws_fopen(recv_filepath, "wb+");
        if (!meta_request->recv_file) {
            aws_translate_and_raise_io_error(errno);
            PyErr_SetAwsLastError();
            goto error;
        }
    }
    if (send_filepath) {
        if (type == AWS_S3_META_REQUEST_TYPE_PUT_OBJECT) {
            /* Copy the http request from python object and replace the old pointer with new pointer */
            meta_request->copied_message = s_copy_http_message(allocator, http_request);
            meta_request->input_body = s_input_stream_new_from_file(allocator, send_filepath, meta_request);
            if (!meta_request->input_body) {
                PyErr_SetAwsLastError();
                goto error;
            }
            /* rewrite the input stream of the original request */
            aws_http_message_set_body_stream(meta_request->copied_message, meta_request->input_body);
        }
    }

    struct aws_s3_meta_request_options s3_meta_request_opt = {
        .type = type,
        .message = meta_request->copied_message ? meta_request->copied_message : http_request,
        .signing_config = credential_provider ? &signing_config : NULL,
        .headers_callback = s_s3_request_on_headers,
        .body_callback = s_s3_request_on_body,
        .finish_callback = s_s3_request_on_finish,
        .shutdown_callback = s_s3_request_on_shutdown,
        .user_data = meta_request,
    };

    if (aws_high_res_clock_get_ticks(&meta_request->last_sampled_time)) {
        goto error;
    }
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

PyObject *aws_py_s3_meta_request_cancel(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_meta_request = NULL;
    if (!PyArg_ParseTuple(args, "O", &py_meta_request)) {
        return NULL;
    }

    struct aws_s3_meta_request *meta_request = NULL;
    meta_request = aws_py_get_s3_meta_request(py_meta_request);
    if (!meta_request) {
        return NULL;
    }

    aws_s3_meta_request_cancel(meta_request);

    Py_RETURN_NONE;
}
