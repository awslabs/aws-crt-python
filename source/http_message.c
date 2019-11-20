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

    /* Dependencies that must outlive this */

    /* InputStream for aws_http_message's aws_input_stream.
     * This is Py_None when no stream is set */
    PyObject *py_body_stream;
};

static void s_http_message_capsule_destructor(PyObject *capsule) {
    struct http_message_binding *message = PyCapsule_GetPointer(capsule, s_capsule_name_http_message);

    /* Note that destructor may be cleaning up a message that failed part-way through initialization */
    aws_http_message_release(message->native);
    Py_XDECREF(message->py_body_stream);

    aws_mem_release(aws_py_get_allocator(), message);
}

static struct http_message_binding *s_binding_from_capsule(PyObject *capsule) {
    return PyCapsule_GetPointer(capsule, s_capsule_name_http_message);
}

struct aws_http_message *aws_py_get_http_message(PyObject *http_message) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        http_message, s_capsule_name_http_message, "HttpMessageBase", http_message_binding);
}

/* Common logic for creating a binding around a new request or existing request */
static PyObject *s_common_new_binding(struct aws_http_message *existing_request) {
    struct aws_allocator *alloc = aws_py_get_allocator();
    struct http_message_binding *request = aws_mem_calloc(alloc, 1, sizeof(struct http_message_binding));
    if (!request) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructors will clean up anything stored inside them.
     *
     * This function will return BOTH the request-binding-capsule AND the headers-binding-capsule */
    PyObject *py_message_capsule = NULL;
    PyObject *py_headers_capsule = NULL;

    py_message_capsule = PyCapsule_New(request, s_capsule_name_http_message, s_http_message_capsule_destructor);
    if (!py_message_capsule) {
        goto error;
    }

    if (existing_request) {
        request->native = existing_request;
        aws_http_message_acquire(request->native);
    } else {
        request->native = aws_http_message_new_request(alloc);
        if (!request->native) {
            goto error;
        }
    }

    /* Default py_body_stream ref to None, not NULL */
    request->py_body_stream = Py_None;
    Py_INCREF(request->py_body_stream);

    /* In C, the aws_http_message owns an aws_http_headers.
     * Likewise, in Python, the HttpMessageBase class owns an HttpHeaders.
     * Create the capsule for each of these classes here. */
    py_headers_capsule = aws_py_http_headers_new_from_native(aws_http_message_get_headers(request->native));
    if (!py_headers_capsule) {
        goto error;
    }

    /* Return (capsule, headers_capsule) */
    PyObject *py_return_tuple = PyTuple_New(2);
    if (!py_return_tuple) {
        goto error;
    }
    PyTuple_SET_ITEM(py_return_tuple, 0, py_message_capsule);
    PyTuple_SET_ITEM(py_return_tuple, 1, py_headers_capsule);
    return py_return_tuple;

error:
    if (py_message_capsule) {
        Py_DECREF(py_message_capsule);
    } else {
        aws_mem_release(alloc, request);
    }
    Py_XDECREF(py_headers_capsule);
    return NULL;
}

PyObject *aws_py_http_message_new_request(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;
    return s_common_new_binding(NULL);
}

PyObject *aws_py_http_message_new_request_from_native(struct aws_http_message *request) {
    return s_common_new_binding(request);
}

static struct http_message_binding *s_get_binding_from_capsule_arg(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {
        return NULL;
    }
    return s_binding_from_capsule(py_capsule);
}

PyObject *aws_py_http_message_get_request_method(PyObject *self, PyObject *args) {
    struct http_message_binding *binding = s_get_binding_from_capsule_arg(self, args);
    if (!binding) {
        return NULL;
    }

    struct aws_byte_cursor method;
    if (aws_http_message_get_request_method(binding->native, &method)) {
        Py_RETURN_NONE;
    }

    return PyString_FromAwsByteCursor(&method);
}

PyObject *aws_py_http_message_set_request_method(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_capsule;
    struct aws_byte_cursor method;
    if (!PyArg_ParseTuple(args, "Os#", &py_capsule, &method.ptr, &method.len)) {
        return NULL;
    }

    struct http_message_binding *binding = s_binding_from_capsule(py_capsule);
    if (!binding) {
        return NULL;
    }

    if (aws_http_message_set_request_method(binding->native, method)) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_message_get_request_path(PyObject *self, PyObject *args) {
    struct http_message_binding *binding = s_get_binding_from_capsule_arg(self, args);
    if (!binding) {
        return NULL;
    }

    struct aws_byte_cursor path;
    if (aws_http_message_get_request_path(binding->native, &path)) {
        Py_RETURN_NONE;
    }
    return PyString_FromAwsByteCursor(&path);
}

PyObject *aws_py_http_message_set_request_path(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_capsule;
    struct aws_byte_cursor path;
    if (!PyArg_ParseTuple(args, "Os#", &py_capsule, &path.ptr, &path.len)) {
        return NULL;
    }

    struct http_message_binding *binding = s_binding_from_capsule(py_capsule);
    if (!binding) {
        return NULL;
    }

    if (aws_http_message_set_request_path(binding->native, path)) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_message_get_body_stream(PyObject *self, PyObject *args) {
    struct http_message_binding *binding = s_get_binding_from_capsule_arg(self, args);
    if (!binding) {
        return NULL;
    }

    Py_INCREF(binding->py_body_stream);
    return binding->py_body_stream;
}

PyObject *aws_py_http_message_set_body_stream(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_capsule;
    PyObject *py_stream;
    if (!PyArg_ParseTuple(args, "OO", &py_capsule, &py_stream)) {
        return NULL;
    }

    struct http_message_binding *binding = s_binding_from_capsule(py_capsule);
    if (!binding) {
        return NULL;
    }

    struct aws_input_stream *stream = NULL;
    if (py_stream != Py_None) {
        stream = aws_py_get_input_stream(py_stream);
        if (!stream) {
            return PyErr_AwsLastError();
        }
    }

    aws_http_message_set_body_stream(binding->native, stream);

    Py_DECREF(binding->py_body_stream);
    binding->py_body_stream = py_stream;
    Py_INCREF(binding->py_body_stream);

    Py_RETURN_NONE;
}
