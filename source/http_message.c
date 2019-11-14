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
#include "http.h"

#include "io.h"
#include <aws/http/request_response.h>
#include <aws/io/stream.h>

static const char *s_capsule_name_http_message = "aws_http_message";

/**
 * Bind aws_http_message to HttpRequest/HttpResponse.
 *
 * This binding acts differently than most. Instead of keeping the native type in
 * sync with the Python type at all times, we lazily sync their contents only when we must.
 * We do this to reduce the impact of repeatedly crossing the language barrier.
 */
struct http_message_binding {
    struct aws_http_message *native;

    /* Native input stream to read from HttpMessage._body_stream */
    struct aws_input_stream *native_body_stream;
};

static void s_http_message_capsule_destructor(PyObject *capsule) {
    struct http_message_binding *message = PyCapsule_GetPointer(capsule, s_capsule_name_http_message);

    /* Note that destructor may be cleaning up a message that failed part-way through initialization */
    aws_http_message_release(message->native);
    aws_input_stream_destroy(message->native_body_stream);

    aws_mem_release(aws_py_get_allocator(), message);
}

static aws_http_message s_binding_from_capsule(PyObject *capsule) {
    return PyCapsule_GetPointer(capsule, s_capsule_name_http_message);
}

struct aws_http_message *aws_py_get_http_message(PyObject *http_message) {
    struct aws_http_message *native = NULL;

    PyObject *capsule = PyObject_GetAttrString(http_message, "_binding");
    if (capsule) {
        struct http_message_binding *message_binding = s_binding_from_capsule(capsule);
        if (message_binding) {
            native = message_binding->native;
        }
        Py_DECREF(capsule);
    }

    return native;
}

PyObject *aws_py_http_request_new(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_body_stream;
    if (!PyArg_ParseTuple(args, "OO", &py_request, &py_body_stream)) {
        return NULL;
    }

    AWS_FATAL_ASSERT(py_request != Py_None);

    struct aws_allocator *alloc = aws_py_get_allocator();
    struct http_message_binding *request = aws_mem_calloc(alloc, 1, sizeof(struct http_message_binding));
    if (!request) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructor will clean up anything stored inside the binding */

    PyObject *headers_capsule = NULL;

    PyObject *capsule = PyCapsule_New(request, s_capsule_name_http_message, s_http_message_capsule_destructor);
    if (!capsule) {
        goto error;
    }

    /* Create native message now, but we don't set its contents till later */
    request->native = aws_http_message_new_request(alloc);
    if (!request->native) {
        goto error;
    }

    request->self_proxy = PyWeakref_NewProxy(py_request, NULL);
    if (!request->self_proxy) {
        goto error;
    }

    /* If HttpMessage._body_stream set, create native aws_input_stream to read from it. */
    if (py_body_stream != Py_None) {
        request->native_body_stream = aws_input_stream_new_from_py(py_body_stream);
        if (!request->native_body_stream) {
            PyErr_SetAwsLastError();
            goto error;
        }

        aws_http_message_set_body_stream(request->native, request->native_body_stream);
    }

    /* In C, the aws_http_message owns an aws_http_headers.
     * Likewise, in Python, the HttpMessageBase class owns an HttpHeaders.
     * Create the capsule for each of these classes here. */
    headers_capsule = aws_py_http_headers_new_from_native(aws_http_message_get_headers(request->native));
    if (!headers_capsule) {
        goto error;
    }

    /* Return (capsule, headers_capsule) */
    PyObject *return_tuple = PyTuple_New(2);
    if (!return_tuple) {
        goto error;
    }

    PyTuple_SET_ITEM(return_tuple, 0, capsule);
    PyTuple_SET_ITEM(return_tuple, 1, headers_tuple);
    return return_tuple;

error:
    Py_XDECREF(headers_capsule);
    if (capsule) {
        Py_DECREF(capsule);
    } else {
        aws_mem_release(alloc, request);
    }
    return NULL;
}

PyObject *aws_py_http_message_get_request_method(PyObject *self, PyObject *args) {


    (void)self;
    (void)args;
    return NULL;
}

PyObject *aws_py_http_message_set_request_method(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    return NULL;
}

PyObject *aws_py_http_message_get_request_path(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    return NULL;
}

PyObject *aws_py_http_message_set_request_path(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    return NULL;
}
