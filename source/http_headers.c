/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "http.h"

#include <aws/http/request_response.h>

static const char *s_capsule_name_headers = "aws_http_headers";

/* HttpHeaders._binding capsule contains raw aws_http_headers struct.
 * There is no intermediate binding struct */

static struct aws_http_headers *s_headers_from_capsule(PyObject *py_capsule) {
    return PyCapsule_GetPointer(py_capsule, s_capsule_name_headers);
}

/* Runs when GC destroys the capsule */
static void s_headers_capsule_destructor(PyObject *py_capsule) {
    struct aws_http_headers *headers = s_headers_from_capsule(py_capsule);
    aws_http_headers_release(headers);
}

struct aws_http_headers *aws_py_get_http_headers(PyObject *http_headers) {
    return aws_py_get_binding(http_headers, s_capsule_name_headers, "HttpHeaders");
}

PyObject *aws_py_http_headers_new_from_native(struct aws_http_headers *headers) {
    PyObject *py_capsule = PyCapsule_New(headers, s_capsule_name_headers, s_headers_capsule_destructor);
    if (!py_capsule) {
        return NULL;
    }

    /* Acquire hold so aws_http_headers object lives at least as long as the binding */
    aws_http_headers_acquire(headers);
    return py_capsule;
}

PyObject *aws_py_http_headers_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_http_headers *headers = aws_http_headers_new(aws_py_get_allocator());
    if (!headers) {
        return PyErr_AwsLastError();
    }

    PyObject *py_capsule = PyCapsule_New(headers, s_capsule_name_headers, s_headers_capsule_destructor);
    if (!py_capsule) {
        aws_http_headers_release(headers);
        return NULL;
    }

    return py_capsule;
}

/**
 * Common start to methods whose first argument is the capsule.
 * FMT: string for PyArg_ParseTuple(). DO NOT pass the "O" for the capsule.
 * ...: varargs for PyArg_ParseTuple(). DO NOT pass &capsule.
 *
 * on error, returns NULL from function with python exception set
 * on success, creates and sets local variable: aws_http_headers *headers = ...;
 */
#define S_HEADERS_METHOD_START(FMT, ...)                                                                               \
    (void)self;                                                                                                        \
    PyObject *py_capsule;                                                                                              \
    if (!PyArg_ParseTuple(args, "O" FMT, &py_capsule, __VA_ARGS__)) {                                                  \
        return NULL;                                                                                                   \
    }                                                                                                                  \
    struct aws_http_headers *headers = s_headers_from_capsule(py_capsule);                                             \
    if (!headers) {                                                                                                    \
        return NULL;                                                                                                   \
    }

PyObject *aws_py_http_headers_add(PyObject *self, PyObject *args) {
    struct aws_byte_cursor name;
    struct aws_byte_cursor value;
    S_HEADERS_METHOD_START("s#s#", &name.ptr, &name.len, &value.ptr, &value.len);

    if (aws_http_headers_add(headers, name, value)) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_headers_add_pairs(PyObject *self, PyObject *args) {
    PyObject *py_pairs;
    S_HEADERS_METHOD_START("O", &py_pairs);
    bool success = false;

    const char *type_errmsg = "List of (name,value) pairs expected.";
    PyObject *py_sequence = PySequence_Fast(py_pairs, type_errmsg); /* new reference */
    if (!py_sequence) {
        return NULL;
    }

    const Py_ssize_t count = PySequence_Fast_GET_SIZE(py_sequence);
    for (Py_ssize_t i = 0; i < count; ++i) {
        /* XYZ_GET_ITEM() calls returns borrowed references */
        PyObject *py_pair = PySequence_Fast_GET_ITEM(py_sequence, i);

        if (!PyTuple_Check(py_pair) || PyTuple_GET_SIZE(py_pair) != 2) {
            PyErr_SetString(PyExc_TypeError, type_errmsg);
            goto done;
        }

        struct aws_byte_cursor name = aws_byte_cursor_from_pyunicode(PyTuple_GET_ITEM(py_pair, 0));
        struct aws_byte_cursor value = aws_byte_cursor_from_pyunicode(PyTuple_GET_ITEM(py_pair, 1));
        if (!name.ptr || !value.ptr) {
            PyErr_SetString(PyExc_TypeError, type_errmsg);
            goto done;
        }

        if (aws_http_headers_add(headers, name, value)) {
            PyErr_SetAwsLastError();
            goto done;
        }
    }

    success = true;
done:
    Py_DECREF(py_sequence);
    if (success) {
        Py_RETURN_NONE;
    }
    return NULL;
}

PyObject *aws_py_http_headers_set(PyObject *self, PyObject *args) {
    struct aws_byte_cursor name;
    struct aws_byte_cursor value;
    S_HEADERS_METHOD_START("s#s#", &name.ptr, &name.len, &value.ptr, &value.len);

    if (aws_http_headers_set(headers, name, value)) {
        return PyErr_AwsLastError();
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_headers_get(PyObject *self, PyObject *args) {
    struct aws_byte_cursor name;
    PyObject *py_default;
    S_HEADERS_METHOD_START("s#O", &name.ptr, &name.len, &py_default);

    struct aws_byte_cursor value;
    if (aws_http_headers_get(headers, name, &value)) {
        /* C API raises error if name not found, but Python API returns a default value */
        Py_INCREF(py_default);
        return py_default;
    }

    return PyUnicode_FromAwsByteCursor(&value);
}

static PyObject *s_py_tuple_from_header(struct aws_http_header header) {
    PyObject *py_name = NULL;
    PyObject *py_value = NULL;
    PyObject *py_pair = NULL;

    py_name = PyUnicode_FromAwsByteCursor(&header.name);
    if (!py_name) {
        goto error;
    }

    py_value = PyUnicode_FromAwsByteCursor(&header.value);
    if (!py_value) {
        goto error;
    }

    py_pair = PyTuple_New(2);
    if (!py_pair) {
        goto error;
    }

    PyTuple_SET_ITEM(py_pair, 0, py_name);
    PyTuple_SET_ITEM(py_pair, 1, py_value);
    return py_pair;

error:
    Py_XDECREF(py_name);
    Py_XDECREF(py_value);
    Py_XDECREF(py_pair);
    return NULL;
}

PyObject *aws_py_http_headers_get_index(PyObject *self, PyObject *args) {
    Py_ssize_t index;
    S_HEADERS_METHOD_START("n", &index);

    struct aws_http_header header;
    if (aws_http_headers_get_index(headers, index, &header)) {
        return PyErr_AwsLastError();
    }

    return s_py_tuple_from_header(header);
}

PyObject *aws_py_http_headers_count(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {
        return NULL;
    }

    struct aws_http_headers *headers = s_headers_from_capsule(py_capsule);
    if (!headers) {
        return NULL;
    }

    return PyLong_FromSize_t(aws_http_headers_count(headers));
}

PyObject *aws_py_http_headers_remove(PyObject *self, PyObject *args) {
    struct aws_byte_cursor name;
    S_HEADERS_METHOD_START("s#", &name.ptr, &name.len);

    if (aws_http_headers_erase(headers, name)) {
        PyErr_SetString(PyExc_KeyError, "HttpHeaders.remove(name): name not found");
        return NULL;
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_headers_remove_value(PyObject *self, PyObject *args) {
    struct aws_byte_cursor name;
    struct aws_byte_cursor value;
    S_HEADERS_METHOD_START("s#s#", &name.ptr, &name.len, &value.ptr, &value.len);

    if (aws_http_headers_erase_value(headers, name, value)) {
        PyErr_SetString(PyExc_ValueError, "HttpHeaders.remove_value(name,value): value not found");
        return NULL;
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_http_headers_clear(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {
        return NULL;
    }

    struct aws_http_headers *headers = s_headers_from_capsule(py_capsule);
    if (!headers) {
        return NULL;
    }

    aws_http_headers_clear(headers);

    Py_RETURN_NONE;
}
