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

    /* Weak reference proxy to python self. */
    PyObject *self_proxy;

    /* Native input stream to read from HttpMessage._body_stream */
    struct aws_input_stream *native_body_stream;
};

static void s_http_message_capsule_destructor(PyObject *capsule) {
    struct http_message_binding *message = PyCapsule_GetPointer(capsule, s_capsule_name_http_message);

    /* Note that destructor may be cleaning up a message that failed part-way through initialization */
    aws_http_message_destroy(message->native);
    aws_input_stream_destroy(message->native_body_stream);
    Py_XDECREF(message->self_proxy);

    aws_mem_release(aws_py_get_allocator(), message);
}

/**
 * Update the aws_http_message based on its HttpRequest/HttpResponse Python self.
 * Returns false and sets python error if failure occurred.
 * Note that if failure occurred the aws_http_message might be in a
 * "partially copied" state and should not be used.
 */
static bool s_http_message_update_from_py(struct http_message_binding *message) {

    bool success = false;

    /* Objects that need to be cleaned up whether or not we succeed */
    PyObject *message_self = NULL;
    PyObject *headers = NULL;
    PyObject *map = NULL;
    PyObject *method = NULL;
    PyObject *path = NULL;

    /* Doing a lot of queries so grab a hard reference */
    message_self = PyWeakref_GetObject(message->self_proxy);
    if (message_self == Py_None) {
        PyErr_SetString(PyExc_RuntimeError, "HttpMessageBase destroyed");
        goto done;
    }
    Py_INCREF(message_self);

    headers = PyObject_GetAttrString(message_self, "headers");
    if (!headers) {
        goto done;
    }

    map = PyObject_GetAttrString(headers, "_map");
    if (!map) {
        goto done;
    }

    /* Clear existing headers, before adding the new values. */
    size_t num_headers = aws_http_message_get_header_count(message->native);
    for (size_t i = num_headers; i > 0; --i) { /* erase from back to front */
        aws_http_message_erase_header(message->native, i - 1);
    }

    /* Copy in new header values */
    struct aws_http_header header;
    Py_ssize_t map_pos = 0;
    PyObject *header_name = NULL;
    PyObject *values_list = NULL;
    while (PyDict_Next(map, &map_pos, &header_name, &values_list)) {
        header.name = aws_byte_cursor_from_pystring(header_name);
        if (!header.name.ptr) {
            PyErr_SetString(PyExc_TypeError, "Header name is invalid");
            goto done;
        }

        if (!PyList_Check(values_list)) {
            PyErr_SetString(PyExc_TypeError, "Header values should be in a list");
        }

        Py_ssize_t num_values = PyList_GET_SIZE(values_list);
        for (Py_ssize_t value_i = 0; value_i < num_values; ++value_i) {
            PyObject *name_value_pair = PyList_GET_ITEM(values_list, value_i); /* CANNOT fail, just checked length */

            PyObject *header_value = PyTuple_GetItem(name_value_pair, 1); /* CAN fail, assuming item is 2-tuple */
            if (!header_value) {
                goto done;
            }
            header.value = aws_byte_cursor_from_pystring(header_value);
            if (!header.value.ptr) {
                PyErr_SetString(PyExc_TypeError, "Header value is invalid");
                goto done;
            }

            if (aws_http_message_add_header(message->native, header)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        }
    }

    /* HttpRequest subclass */
    if (aws_http_message_is_request(message->native)) {
        method = PyObject_GetAttrString(message_self, "method");
        struct aws_byte_cursor method_cur = aws_byte_cursor_from_pystring(method);
        if (!method_cur.ptr) {
            PyErr_SetString(PyExc_TypeError, "HttpRequest.method is invalid");
            goto done;
        }
        if (aws_http_message_set_request_method(message->native, method_cur)) {
            PyErr_SetAwsLastError();
            goto done;
        }

        path = PyObject_GetAttrString(message_self, "path");
        struct aws_byte_cursor path_cur = aws_byte_cursor_from_pystring(path);
        if (!path_cur.ptr) {
            PyErr_SetString(PyExc_TypeError, "HttpRequest.path is invalid");
            goto done;
        }
        if (aws_http_message_set_request_path(message->native, path_cur)) {
            PyErr_SetAwsLastError();
            goto done;
        }
    }

    success = true;
done:
    Py_XDECREF(message_self);
    Py_XDECREF(headers);
    Py_XDECREF(map);
    Py_XDECREF(method);
    Py_XDECREF(path);

    return success;
}

struct aws_http_message *aws_py_get_http_message(PyObject *http_message) {
    struct aws_http_message *native = NULL;

    PyObject *capsule = PyObject_GetAttrString(http_message, "_binding");
    if (capsule) {
        struct http_message_binding *message_binding = PyCapsule_GetPointer(capsule, s_capsule_name_http_message);
        if (message_binding) {
            /* Update contents of aws_http_message before returning it */
            if (s_http_message_update_from_py(message_binding)) {
                native = message_binding->native;
                AWS_FATAL_ASSERT(native);
            }
        }
        Py_DECREF(capsule);
    }

    return native;
}

PyObject *aws_py_http_request_new(PyObject *self, PyObject *args) {
    (void)self;

    PyObject *py_request;
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

    return capsule;

error:
    if (capsule) {
        Py_DECREF(capsule);
    } else {
        aws_mem_release(alloc, request);
    }
    return NULL;
}
