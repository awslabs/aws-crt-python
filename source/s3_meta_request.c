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
    if (meta_request->recv_file) {
        fclose(meta_request->recv_file);
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
        PyList_SetItem(header_list, i, tuple); /* steals reference to tuple */
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
    /* If user's callback raises an exception, _S3RequestCore._on_headers
     * stores it to throw later and returns False */
    error = (result == Py_False);
    Py_DECREF(result);
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

/* To avoid reporting progress to python too often. We cache it up and only report to python after at least 1 sec. */
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

    if (request_binding->recv_file) {
        /* The callback will be invoked with the right order, so we don't need to seek first. */
        if (fwrite((void *)body->ptr, body->len, 1, request_binding->recv_file) < 1) {
            int errno_value = ferror(request_binding->recv_file) ? errno : 0; /* Always cache errno  */
            aws_translate_and_raise_io_error_or(errno_value, AWS_ERROR_FILE_WRITE_FAILURE);
            AWS_LOGF_ERROR(
                AWS_LS_S3_META_REQUEST,
                "id=%p Failed writing to file. errno:%d. aws-error:%s",
                (void *)meta_request,
                errno_value,
                aws_error_name(aws_last_error()));
            return AWS_OP_ERR;
        }
        return AWS_OP_SUCCESS;
    }
    bool error = true;
    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    PyObject *result = NULL;
    if (aws_py_gilstate_ensure(&state)) {
        return AWS_OP_ERR; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    result = PyObject_CallMethod(
        request_binding->py_core, "_on_body", "(y#K)", (const char *)(body->ptr), (Py_ssize_t)body->len, range_start);

    if (!result) {
        PyErr_WriteUnraisable(request_binding->py_core);
        goto done;
    }
    /* If user's callback raises an exception, _S3RequestCore._on_body
     * stores it to throw later and returns False */
    error = (result == Py_False);
    Py_DECREF(result);
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

    int error_code = meta_request_result->error_code;

    if (request_binding->recv_file) {
        if (fclose(request_binding->recv_file) != 0) {
            /* Failed to close file, so we can't guarantee it flushed to disk.
             * If the meta-request's error_code was 0, change it to failure */
            if (error_code == 0) {
                int errno_value = errno; /* Always cache errno before potential side-effect */
                aws_translate_and_raise_io_error_or(errno_value, AWS_ERROR_FILE_WRITE_FAILURE);
                error_code = aws_last_error();
                AWS_LOGF_ERROR(
                    AWS_LS_S3_META_REQUEST,
                    "id=%p Failed closing file. errno:%d. aws-error:%s",
                    (void *)meta_request,
                    errno_value,
                    aws_error_name(error_code));
            }
        }
        request_binding->recv_file = NULL;
    }
    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *header_list = NULL;
    PyObject *result = NULL;

    if (request_binding->size_transferred && (error_code == 0)) {
        /* report the remaining progress */
        result =
            PyObject_CallMethod(request_binding->py_core, "_on_progress", "(K)", request_binding->size_transferred);
        if (!result) {
            PyErr_WriteUnraisable(request_binding->py_core);
            /* We MUST keep going and invoke the final callback */
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
            /* We MUST keep going and invoke the final callback. These headers were optional anyway. */
        }
    }
    if (meta_request_result->error_response_body) {
        error_body = *(meta_request_result->error_response_body);
    }

    const char *operation_name = NULL;
    if (meta_request_result->error_response_operation_name != NULL) {
        operation_name = aws_string_c_str(meta_request_result->error_response_operation_name);
    }

    result = PyObject_CallMethod(
        request_binding->py_core,
        "_on_finish",
        "(iiOy#s)",
        error_code,
        meta_request_result->response_status,
        header_list ? header_list : Py_None,
        (const char *)(error_body.buffer),
        (Py_ssize_t)error_body.len,
        operation_name);

    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(request_binding->py_core);
    }

    Py_XDECREF(header_list);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

/* Invoked when S3Request._binding gets cleaned up.
 * DO NOT destroy the C binding struct or anything inside it yet.
 * The user might have let S3Request get GC'd,
 * but the s3_meta_request_binding* must outlive the native aws_s3_meta_request* */
static void s_s3_meta_request_capsule_destructor(PyObject *capsule) {
    struct s3_meta_request_binding *meta_request = PyCapsule_GetPointer(capsule, s_capsule_name_s3_meta_request);

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
    /* Clean thing up before invoking the callback, as the callback means everything has been shutdown, which is not
     * true if we clean the resource after the callback */

    PyObject *py_core = request_binding->py_core;
    Py_INCREF(py_core);
    s_destroy(request_binding);

    /* Deliver the built up list of (name,value) tuples */
    PyObject *result = PyObject_CallMethod(py_core, "_on_shutdown", NULL);
    if (!result) {
        PyErr_WriteUnraisable(py_core);
    }

    Py_XDECREF(py_core);
    PyGILState_Release(state);
    /*************** GIL RELEASE ***************/
}

static void s_s3_request_on_progress(
    struct aws_s3_meta_request *meta_request,
    const struct aws_s3_meta_request_progress *progress,
    void *user_data) {

    (void)meta_request;
    struct s3_meta_request_binding *request_binding = user_data;

    bool report_progress = false;
    s_record_progress(request_binding, progress->bytes_transferred, &report_progress);

    if (report_progress) {
        /*************** GIL ACQUIRE ***************/
        PyGILState_STATE state;
        if (aws_py_gilstate_ensure(&state)) {
            return; /* Python has shut down. Nothing matters anymore, but don't crash */
        }
        PyObject *result =
            PyObject_CallMethod(request_binding->py_core, "_on_progress", "(K)", request_binding->size_transferred);
        if (result) {
            Py_DECREF(result);
        }
        request_binding->size_transferred = 0;
        PyGILState_Release(state);
        /*************** GIL RELEASE ***************/
    }
}

PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *py_s3_request;                           /* O */
    PyObject *s3_client_py;                            /* O */
    PyObject *http_request_py;                         /* O */
    int type;                                          /* i */
    const char *operation_name;                        /* z */
    PyObject *signing_config_py;                       /* O */
    PyObject *credential_provider_py;                  /* O */
    const char *recv_filepath;                         /* z */
    const char *send_filepath;                         /* z */
    struct aws_byte_cursor region;                     /* s# */
    enum aws_s3_checksum_algorithm checksum_algorithm; /* i */
    enum aws_s3_checksum_location checksum_location;   /* i */
    int validate_response_checksum;                    /* p - boolean predicate */
    PyObject *py_core;                                 /* O */
    if (!PyArg_ParseTuple(
            args,
            "OOOizOOzzs#iipO",
            &py_s3_request,
            &s3_client_py,
            &http_request_py,
            &type,
            &operation_name,
            &signing_config_py,
            &credential_provider_py,
            &recv_filepath,
            &send_filepath,
            &region.ptr,
            &region.len,
            &checksum_algorithm,
            &checksum_location,
            &validate_response_checksum,
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

    struct aws_signing_config_aws *signing_config = NULL;
    if (signing_config_py != Py_None) {
        signing_config = aws_py_get_signing_config(signing_config_py);
        if (!signing_config) {
            return NULL;
        }
    }

    struct aws_credentials_provider *credential_provider = NULL;
    if (credential_provider_py != Py_None) {
        credential_provider = aws_py_get_credentials_provider(credential_provider_py);
        if (!credential_provider) {
            return NULL;
        }
    }

    struct aws_signing_config_aws signing_config_from_credentials_provider;
    AWS_ZERO_STRUCT(signing_config_from_credentials_provider);
    if (credential_provider) {
        aws_s3_init_default_signing_config(&signing_config_from_credentials_provider, region, credential_provider);
        signing_config = &signing_config_from_credentials_provider;
    }

    struct aws_s3_checksum_config checksum_config = {
        .checksum_algorithm = checksum_algorithm,
        .location = checksum_location,
        .validate_response_checksum = validate_response_checksum != 0,
    };

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
        meta_request->recv_file = aws_fopen(recv_filepath, "wb");
        if (!meta_request->recv_file) {
            aws_translate_and_raise_io_error(errno);
            PyErr_SetAwsLastError();
            goto error;
        }
    }

    struct aws_s3_meta_request_options s3_meta_request_opt = {
        .type = type,
        .operation_name = aws_byte_cursor_from_c_str(operation_name),
        .message = http_request,
        .signing_config = signing_config,
        .checksum_config = &checksum_config,
        .send_filepath = aws_byte_cursor_from_c_str(send_filepath),
        .headers_callback = s_s3_request_on_headers,
        .body_callback = s_s3_request_on_body,
        .finish_callback = s_s3_request_on_finish,
        .shutdown_callback = s_s3_request_on_shutdown,
        .progress_callback = s_s3_request_on_progress,
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
