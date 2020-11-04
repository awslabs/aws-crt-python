/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "event_stream.h"

#include <aws/event-stream/event_stream.h>

/* Add new header to aws_array_list, based on python header */
static bool s_add_header(struct aws_array_list *headers, PyObject *header_py) {
    bool success = false;

    /* Here's every new reference we may create. These need to be decref'd at end of function */
    PyObject *name_py = NULL;               /* EventStreamHeaders.name */
    PyObject *type_py = NULL;               /* EventStreamHeaders.type */
    PyObject *type_value_py = NULL;         /* EventStreamHeaders.type.value */
    PyObject *value_py = NULL;              /* EventStreamHeaders.value */
    PyObject *value_extra_py = NULL;        /* EventStreamHeaders.value.some_extra_property  */
    Py_buffer value_buf_py = {.obj = NULL}; /* For reading bytes-like values */

    name_py = PyObject_GetAttrString(header_py, "name"); /* New reference */
    if (!name_py) {
        goto done;
    }

    size_t name_len;
    const char *name = PyUnicode_AsUTF8AndSize(name_py, (Py_ssize_t *)&name_len);
    if (!name) {
        goto done;
    }

    const size_t name_len_max = sizeof(((struct aws_event_stream_header_value_pair *)0)->header_name) - 1;
    if (name_len > name_len_max) {
        PyErr_SetString(PyExc_ValueError, "EventStreamHeader.name exceeds max length");
        goto done;
    }

    type_py = PyObject_GetAttrString(header_py, "type"); /* New reference */
    if (!type_py) {
        goto done;
    }

    type_value_py = PyObject_GetAttrString(type_py, "value"); /* New reference */
    if (!type_value_py) {
        goto done;
    }

    int type = PyLong_AsLong(type_value_py);
    if (PyErr_Occurred()) {
        goto done;
    }

    value_py = PyObject_GetAttrString(header_py, "value"); /* New reference */
    if (!value_py) {
        goto done;
    }

    switch (type) {
        case AWS_EVENT_STREAM_HEADER_BOOL_TRUE: {
            if (aws_event_stream_add_bool_header(headers, name, name_len, true)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_BOOL_FALSE: {
            if (aws_event_stream_add_bool_header(headers, name, name_len, false)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_BYTE: {
            int32_t value = PyLong_AsLong(value_py);
            if (PyErr_Occurred()) {
                goto done;
            }
            /* simply casting to 8 bits, we already checked bounds when setting value in python */
            if (aws_event_stream_add_byte_header(headers, name, name_len, (int8_t)value)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_INT16: {
            int32_t value = PyLong_AsLong(value_py);
            if (PyErr_Occurred()) {
                goto done;
            }
            /* simply casting to 16 bits, we already checked bounds when setting value in python */
            if (aws_event_stream_add_int16_header(headers, name, name_len, (int16_t)value)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_INT32: {
            int32_t value = PyLong_AsLong(value_py);
            if (PyErr_Occurred()) {
                goto done;
            }
            if (aws_event_stream_add_int32_header(headers, name, name_len, value)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_INT64: {
            int64_t value = PyLong_AsLongLong(value_py);
            if (PyErr_Occurred()) {
                goto done;
            }
            if (aws_event_stream_add_int64_header(headers, name, name_len, value)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_BYTE_BUF: {
            if (PyObject_GetBuffer(value_py, &value_buf_py, PyBUF_SIMPLE) == -1) { /* New reference */
                goto done;
            }
            if (aws_event_stream_add_bytebuf_header(
                    headers, name, name_len, value_buf_py.buf, value_buf_py.len, true /*copy*/)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_STRING: {
            size_t value_len;
            const char *value = PyUnicode_AsUTF8AndSize(value_py, (Py_ssize_t *)&value_len);
            if (!value) {
                goto done;
            }
            if (value_len > UINT16_MAX) {
                PyErr_SetString(PyExc_ValueError, "EventStreamHeader STRING value exceeds max length");
                goto done;
            }
            if (aws_event_stream_add_string_header(
                    headers, name, name_len, value, (uint16_t)value_len, true /*copy*/)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_TIMESTAMP: {
            int64_t value = PyLong_AsLongLong(value_py);
            if (PyErr_Occurred()) {
                goto done;
            }
            if (aws_event_stream_add_timestamp_header(headers, name, name_len, value)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        case AWS_EVENT_STREAM_HEADER_UUID: {
            value_extra_py = PyObject_GetAttrString(value_py, "bytes"); /* New reference */
            if (!value_extra_py) {
                goto done;
            }
            if (PyObject_GetBuffer(value_extra_py, &value_buf_py, PyBUF_SIMPLE) == -1) { /* New reference */
                goto done;
            }
            if (value_buf_py.len != 16) {
                PyErr_SetString(PyExc_ValueError, "UUID.bytes must be length 16");
                goto done;
            }
            if (aws_event_stream_add_uuid_header(headers, name, name_len, (const uint8_t *)value_buf_py.buf)) {
                PyErr_SetAwsLastError();
                goto done;
            }
        } break;

        default: {
            PyErr_SetString(PyExc_ValueError, "EventStreamHeader.type has invalid value");
            goto done;
        } break;
    }

    success = true;
done:
    Py_XDECREF(name_py);
    Py_XDECREF(type_py);
    Py_XDECREF(type_value_py);
    Py_XDECREF(value_py);
    Py_XDECREF(value_extra_py);
    if (value_buf_py.obj) {
        PyBuffer_Release(&value_buf_py);
    }
    return success;
}

bool aws_py_event_stream_headers_list_init(struct aws_array_list *headers, PyObject *headers_py) {
    if (aws_event_stream_headers_list_init(headers, aws_py_get_allocator())) {
        PyErr_SetAwsLastError();
        return false;
    }

    /* From hereon, need to clean up if anything goes wrong */
    bool success = false;
    PyObject *sequence_py = NULL;

    sequence_py = PySequence_Fast(headers_py, "Expected sequence of EventStreamHeaders");
    if (!sequence_py) {
        goto done;
    }

    const Py_ssize_t count = PySequence_Fast_GET_SIZE(sequence_py);
    for (Py_ssize_t i = 0; i < count; ++i) {
        /* Borrowed reference, don't need to decref */
        PyObject *header_py = PySequence_Fast_GET_ITEM(sequence_py, i);

        if (!s_add_header(headers, header_py)) {
            goto done;
        }
    }

    success = true;
done:
    Py_XDECREF(sequence_py);

    if (success) {
        return true;
    }

    aws_event_stream_headers_list_cleanup(headers);
    return false;
}

/* Create python value from header value */
static PyObject *s_create_value(struct aws_event_stream_header_value_pair *header) {
    switch (header->header_value_type) {
        case AWS_EVENT_STREAM_HEADER_BOOL_TRUE:
            Py_INCREF(Py_True);
            return Py_True;

        case AWS_EVENT_STREAM_HEADER_BOOL_FALSE:
            Py_INCREF(Py_False);
            return Py_False;

        case AWS_EVENT_STREAM_HEADER_BYTE:
            return PyLong_FromLong(aws_event_stream_header_value_as_byte(header));

        case AWS_EVENT_STREAM_HEADER_INT16:
            return PyLong_FromLong(aws_event_stream_header_value_as_int16(header));

        case AWS_EVENT_STREAM_HEADER_INT32:
            return PyLong_FromLong(aws_event_stream_header_value_as_int32(header));

        case AWS_EVENT_STREAM_HEADER_INT64:
            return PyLong_FromLong(aws_event_stream_header_value_as_int64(header));

        case AWS_EVENT_STREAM_HEADER_BYTE_BUF: {
            struct aws_byte_buf tmp_buf = aws_event_stream_header_value_as_bytebuf(header);
            return PyBytes_FromStringAndSize((const char *)tmp_buf.buffer, tmp_buf.len);
        }

        case AWS_EVENT_STREAM_HEADER_STRING: {
            struct aws_byte_buf tmp_buf = aws_event_stream_header_value_as_string(header);
            return PyUnicode_FromStringAndSize((const char *)tmp_buf.buffer, tmp_buf.len);
        }

        case AWS_EVENT_STREAM_HEADER_TIMESTAMP:
            return PyLong_FromLong(aws_event_stream_header_value_as_timestamp(header));

        case AWS_EVENT_STREAM_HEADER_UUID: {
            /* It's tricky to create a python UUID with the c-api.
             * Instead, create python bytes and transform that into an actual UUID out in python */
            struct aws_byte_buf tmp_buf = aws_event_stream_header_value_as_uuid(header);
            return PyBytes_FromStringAndSize((const char *)tmp_buf.buffer, tmp_buf.len);
        }
    }

    PyErr_SetString(PyExc_ValueError, "Invalid aws_event_stream_header_value_type");
    return NULL;
}

PyObject *aws_py_event_stream_headers_create_python_list(
    struct aws_event_stream_header_value_pair *headers,
    size_t count) {

    PyObject *list_py = PyList_New(count);
    if (!list_py) {
        return NULL;
    }

    /* From hereon, need to clean up if anything goes wrong */

    for (size_t i = 0; i < count; ++i) {
        struct aws_event_stream_header_value_pair *header = &headers[i];

        /* NOTE: Py_BuildValue() will fail if it gets NULL from s_create_value().
         * This is a cool feature, don't need to worry about cleaning up tmp value if something goes wrong. */

        PyObject *tuple = Py_BuildValue(
            "(s#iO)", header->header_name, header->header_name_len, header->header_value_type, s_create_value(header));
        if (!tuple) {
            goto error;
        }

        PyList_SET_ITEM(list_py, i, tuple); /* steals reference to tuple */
    }

    return list_py;
error:
    Py_DECREF(list_py);
    return NULL;
}
