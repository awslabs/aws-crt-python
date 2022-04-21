/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
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
};

static void s_http_message_capsule_destructor(PyObject *capsule) {
    struct http_message_binding *message = PyCapsule_GetPointer(capsule, s_capsule_name_http_message);

    /* Note that destructor may be cleaning up a message that failed part-way through initialization */
    aws_http_message_release(message->native);

    aws_mem_release(aws_py_get_allocator(), message);
}

static struct http_message_binding *s_binding_from_capsule(PyObject *capsule) {
    return PyCapsule_GetPointer(capsule, s_capsule_name_http_message);
}

struct aws_http_message *aws_py_get_http_message(PyObject *http_message) {
    AWS_PY_RETURN_NATIVE_FROM_BINDING(
        http_message, s_capsule_name_http_message, "HttpMessageBase", http_message_binding);
}

PyObject *aws_py_http_message_new_request_from_native(struct aws_http_message *request) {
    struct aws_allocator *alloc = aws_py_get_allocator();
    struct http_message_binding *binding = aws_mem_calloc(alloc, 1, sizeof(struct http_message_binding));
    if (!binding) {
        return PyErr_AwsLastError();
    }

    /* From hereon, we need to clean up if errors occur.
     * Fortunately, the capsule destructors will clean up anything stored inside them. */
    PyObject *py_capsule = PyCapsule_New(binding, s_capsule_name_http_message, s_http_message_capsule_destructor);
    if (!py_capsule) {
        goto error;
    }

    binding->native = request;
    aws_http_message_acquire(binding->native);

    return py_capsule;

error:
    if (py_capsule) {
        Py_DECREF(py_capsule);
    } else {
        aws_mem_release(alloc, binding);
    }
    return NULL;
}

PyObject *aws_py_http_message_new_request(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_headers;
    if (!PyArg_ParseTuple(args, "O", &py_headers)) {
        return NULL;
    }

    struct aws_http_headers *headers = aws_py_get_http_headers(py_headers);
    if (!headers) {
        return NULL;
    }

    struct aws_http_message *request = aws_http_message_new_request_with_headers(aws_py_get_allocator(), headers);
    if (!request) {
        return PyErr_AwsLastError();
    }

    PyObject *py_capsule = aws_py_http_message_new_request_from_native(request);
    if (!py_capsule) {
        aws_http_message_release(request);
        return NULL;
    }

    /* The capsule has its own reference to the request now,
     * release the reference we got for creating it */
    aws_http_message_release(request);

    return py_capsule;
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

    return PyUnicode_FromAwsByteCursor(&method);
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
    return PyUnicode_FromAwsByteCursor(&path);
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

    Py_RETURN_NONE;
}
