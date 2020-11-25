/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "s3_client.h"

#include "auth.h"
#include "http.h"
#include "io.h"

#include <aws/http/request_response.h>
#include <aws/io/stream.h>

static const char *s_capsule_name_s3_meta_request = "aws_s3_meta_request";

struct s3_meta_request_binding {
    struct aws_s3_meta_request *native;

    bool release_called;
    bool shutdown_called;

    /* Weak reference proxy to python self.
     * NOTE: The python self is forced to stay alive until on_finish fires.
     * We do this by INCREFing when the object is created, and DECREFing when on_finish fires. */
    PyObject *self_proxy;

    /* Shutdown callback, all resource cleaned up, reference cleared after invoke */
    PyObject *on_shutdown;

    // /* for test */
    // FILE *input_file;
    // struct aws_byte_buf test_buffer;
    // struct aws_byte_cursor test_body_cursor;
    // struct aws_input_stream *input_stream;
};

// void aws_s3_create_test_buffer(struct aws_allocator *allocator, size_t buffer_size, struct aws_byte_buf *out_buf) {
//     AWS_PRECONDITION(allocator);
//     AWS_PRECONDITION(out_buf);

//     struct aws_byte_cursor test_string = AWS_BYTE_CUR_INIT_FROM_STRING_LITERAL("This is an S3 test.");

//     aws_byte_buf_init(out_buf, allocator, buffer_size);

//     for (size_t buffer_pos = 0; buffer_pos < buffer_size; buffer_pos += test_string.len) {
//         size_t buffer_size_remaining = buffer_size - buffer_pos;
//         size_t string_copy_size = test_string.len;

//         if (buffer_size_remaining < string_copy_size) {
//             string_copy_size = buffer_size_remaining;
//         }

//         struct aws_byte_cursor from_byte_cursor = {.len = string_copy_size, .ptr = test_string.ptr};

//         aws_byte_buf_append(out_buf, &from_byte_cursor);
//     }
// }

static void s_s3_meta_request_release(struct s3_meta_request_binding *meta_request) {
    AWS_FATAL_ASSERT(!meta_request->release_called);
    printf("s_s3_meta_request_release\n");
    meta_request->release_called = true;

    bool destroy_after_release = meta_request->shutdown_called;

    aws_s3_meta_request_release(meta_request->native);

    if (destroy_after_release) {
        aws_mem_release(aws_py_get_allocator(), meta_request);
    }
}

static void s_s3_request_on_headers(
    struct aws_s3_meta_request *meta_request,
    struct aws_http_headers *headers,
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
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto done;
    }

    for (size_t i = 0; i < num_headers; i++) {
        struct aws_http_header header;
        AWS_ZERO_STRUCT(header);
        if (aws_http_headers_get_index(headers, i, &header)) {
            goto done;
        }
        const char *name_str = (const char *)header.name.ptr;
        size_t name_len = header.name.len;
        const char *value_str = (const char *)header.value.ptr;
        size_t value_len = header.value.len;
        PyObject *tuple = Py_BuildValue("(s#s#)", name_str, name_len, value_str, value_len);
        if (!tuple) {
            PyErr_WriteUnraisable(PyErr_Occurred());
            goto done;
        }
        PyList_SET_ITEM(header_list, i, tuple); /* steals reference to tuple */
    }

    /* Deliver the built up list of (name,value) tuples */
    PyObject *result =
        PyObject_CallMethod(request_binding->self_proxy, "_on_headers", "(iO)", response_status, header_list);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
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
    uint64_t range_end,
    void *user_data) {
    (void)meta_request;
    (void)range_end;
    (void)range_start;
    struct s3_meta_request_binding *request_binding = user_data;

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }

    PyObject *result = PyObject_CallMethod(
        request_binding->self_proxy, "_on_body", "(y#)", (const char *)(body->ptr), (Py_ssize_t)body->len);
    if (!result) {
        PyErr_WriteUnraisable(PyErr_Occurred());
        goto done;
    }
    Py_DECREF(result);

done:
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

    /*************** GIL ACQUIRE ***************/
    PyGILState_STATE state;
    if (aws_py_gilstate_ensure(&state)) {
        return; /* Python has shut down. Nothing matters anymore, but don't crash */
    }
    /* TODO: expose the error_response_headers/body */
    PyObject *result =
        PyObject_CallMethod(request_binding->self_proxy, "_on_finish", "(i)", meta_request_result->error_code);
    if (result) {
        Py_DECREF(result);
    } else {
        /* Callback might fail during application shutdown */
        PyErr_WriteUnraisable(PyErr_Occurred());
    }
    printf("before decref self_proxy\n");
    /* DECREF python self, we don't need to force it to stay alive any longer. */
    // Py_DECREF(PyWeakref_GetObject(request_binding->self_proxy));
    printf("after decref self_proxy\n");
    PyGILState_Release(state);
    printf("after release state\n");
    /*************** GIL RELEASE ***************/
    // aws_input_stream_destroy(request_binding->input_stream);
    // fclose(request_binding->input_file);
    // aws_byte_buf_clean_up(&request_binding->test_buffer);
}

/* Invoked when the python object get cleaned up */
static void s_s3_meta_request_capsule_destructor(PyObject *capsule) {
    printf("s_s3_meta_request_capsule_destructor\n");
    struct s3_meta_request_binding *meta_request = PyCapsule_GetPointer(capsule, s_capsule_name_s3_meta_request);
    Py_XDECREF(meta_request->self_proxy);
    s_s3_meta_request_release(meta_request);
}

/* Callback from C land, invoked when the underlying shutdown process finished */
static void s_s3_request_on_shutdown(void *user_data) {
    printf("s_s3_request_on_shutdown\n");
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

PyObject *aws_py_s3_client_make_meta_request(PyObject *self, PyObject *args) {
    (void)self;

    struct aws_allocator *allocator = aws_py_get_allocator();

    PyObject *py_s3_request = NULL;
    PyObject *s3_client_py = NULL;
    PyObject *http_request_py = NULL;
    int type;
    PyObject *on_headers_py = NULL;
    PyObject *on_body_py = NULL;
    PyObject *on_finish_py = NULL;
    PyObject *on_shutdown_py = NULL;
    if (!PyArg_ParseTuple(
            args,
            "OOOiOOOO",
            &py_s3_request,
            &s3_client_py,
            &http_request_py,
            &type,
            &on_headers_py,
            &on_body_py,
            &on_finish_py,
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

    struct s3_meta_request_binding *meta_request = aws_mem_calloc(allocator, 1, sizeof(struct s3_meta_request_binding));
    if (!meta_request) {
        return PyErr_AwsLastError();
    }
    // aws_byte_buf_init(&meta_request->test_buffer, allocator, 10 * 1024 * 1024);
    // struct aws_input_stream *stream = aws_http_message_get_body_stream(http_request);
    // int64_t len = 0;
    // stream->vtable->get_length(stream, &len);
    // struct aws_stream_status status;
    // printf("buffer length before read   %d\n", (int)meta_request->test_buffer.len);
    // stream->vtable->read(stream, &meta_request->test_buffer);
    // stream->vtable->get_status(stream, &status);
    // printf("%p\n", stream);
    // printf("stream length from python before read %lld\n", len);
    // printf("stream status %d   %d\n", (int)status.is_end_of_stream, (int)status.is_valid);
    // printf("buffer length after read   %d\n", (int)meta_request->test_buffer.len);
    // stream->vtable->get_length(stream, &len);
    // printf("stream length after read   %lld\n", len);

    // aws_s3_create_test_buffer(allocator, 10 * 1024 * 1024, &meta_request->test_buffer);
    // meta_request->input_file = fopen("put_object_test_10MB.txt", "rb");

    // meta_request->test_body_cursor = aws_byte_cursor_from_buf(&meta_request->test_buffer);
    // meta_request->input_stream = aws_input_stream_new_from_open_file(allocator, meta_request->input_file);
    // aws_http_message_set_body_stream(http_request, meta_request->input_stream);
    // len = 0;
    // meta_request->input_stream->vtable->get_length(meta_request->input_stream, &len);
    // printf("stream length from C %lld\n", len);
    /* From hereon, we need to clean up if errors occur */
    struct aws_s3_meta_request_options s3_meta_request_opt = {
        .type = type,
        .message = http_request,
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

    PyObject *capsule =
        PyCapsule_New(meta_request, s_capsule_name_s3_meta_request, s_s3_meta_request_capsule_destructor);
    if (!capsule) {
        goto capsule_new_failed;
    }

    meta_request->self_proxy = PyWeakref_NewProxy(py_s3_request, NULL);
    if (!meta_request->self_proxy) {
        goto proxy_failed;
    }

    meta_request->on_shutdown = on_shutdown_py;
    Py_INCREF(meta_request->on_shutdown);

    return capsule;

proxy_failed:
    Py_DECREF(capsule);
capsule_new_failed:
    aws_s3_meta_request_release(meta_request->native);
error:
    aws_mem_release(allocator, meta_request);
    return NULL;
}
