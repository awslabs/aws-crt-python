/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "cbor.h"

#include <aws/common/cbor.h>

/*******************************************************************************
 * ENCODE
 ******************************************************************************/

static const char *s_capsule_name_cbor_encoder = "aws_cbor_encoder";

static struct aws_cbor_encoder *s_cbor_encoder_from_capsule(PyObject *py_capsule) {
    return PyCapsule_GetPointer(py_capsule, s_capsule_name_cbor_encoder);
}

/* Runs when GC destroys the capsule */
static void s_cbor_encoder_capsule_destructor(PyObject *py_capsule) {
    struct aws_cbor_encoder *encoder = s_cbor_encoder_from_capsule(py_capsule);
    aws_cbor_encoder_release(encoder);
}

PyObject *aws_py_cbor_encoder_new(PyObject *self, PyObject *args) {
    (void)self;
    (void)args;

    struct aws_cbor_encoder *encoder = aws_cbor_encoder_new(aws_py_get_allocator(), 128);
    AWS_ASSERT(encoder != NULL);
    PyObject *py_capsule = PyCapsule_New(encoder, s_capsule_name_cbor_encoder, s_cbor_encoder_capsule_destructor);
    if (!py_capsule) {
        aws_cbor_encoder_release(encoder);
        return NULL;
    }

    return py_capsule;
}
#define S_ENCODER_METHOD_START(FMT, ...)                                                                               \
    (void)self;                                                                                                        \
    PyObject *py_capsule;                                                                                              \
    if (!PyArg_ParseTuple(args, "O" FMT, &py_capsule, __VA_ARGS__)) {                                                  \
        return NULL;                                                                                                   \
    }                                                                                                                  \
    struct aws_cbor_encoder *encoder = s_cbor_encoder_from_capsule(py_capsule);                                        \
    if (!encoder) {                                                                                                    \
        return NULL;                                                                                                   \
    }

PyObject *aws_py_cbor_encoder_get_encoded_data(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {
        return NULL;
    }
    struct aws_cbor_encoder *encoder = s_cbor_encoder_from_capsule(py_capsule);
    if (!encoder) {
        return NULL;
    }
    struct aws_byte_cursor encoded_data = aws_cbor_encoder_get_encoded_data(encoder);
    if (encoded_data.len == 0) {
        /* TODO: probably better to be empty instead of None?? */
        Py_RETURN_NONE;
    }
    return PyBytes_FromStringAndSize((const char *)encoded_data.ptr, encoded_data.len);
}

PyObject *aws_py_cbor_encoder_encode_unsigned_int(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    AWS_ASSERT(!PyErr_Occurred());
    aws_cbor_encode_uint(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_negative_int(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    AWS_ASSERT(!PyErr_Occurred());
    aws_cbor_encode_negint(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_float(PyObject *self, PyObject *args) {
    PyObject *pyfloat;
    S_ENCODER_METHOD_START("O", &pyfloat);
    double data = PyFloat_AsDouble(pyfloat);
    /* Rely on the python convert to check the pyfloat is able to convert to double. */
    if (PyErr_Occurred()) {
        PyErr_SetString(PyExc_ValueError, "AwsCborEncoder.add_float is not a valid double to encode");
        return NULL;
    }
    aws_cbor_encode_double(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_bytes(PyObject *self, PyObject *args) {
    struct aws_byte_cursor bytes_data;
    S_ENCODER_METHOD_START("y#", &bytes_data.ptr, &bytes_data.len);
    aws_cbor_encode_bytes(encoder, bytes_data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_str(PyObject *self, PyObject *args) {
    struct aws_byte_cursor str_data;
    S_ENCODER_METHOD_START("s#", &str_data.ptr, &str_data.len);
    aws_cbor_encode_string(encoder, str_data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_array_start(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    AWS_ASSERT(!PyErr_Occurred());
    aws_cbor_encode_array_start(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_map_start(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    AWS_ASSERT(!PyErr_Occurred());
    aws_cbor_encode_map_start(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_tag(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    AWS_ASSERT(!PyErr_Occurred());
    aws_cbor_encode_tag(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_encode_simple_types(PyObject *self, PyObject *args) {
    Py_ssize_t type_enum;
    S_ENCODER_METHOD_START("n", &type_enum);
    switch (type_enum) {
        case 5:
            aws_cbor_encode_null(encoder);
            break;

        default:
            Py_RETURN_NONE;
            break;
    }
    Py_RETURN_NONE;
}

/*******************************************************************************
 * DECODE
 ******************************************************************************/

static const char *s_capsule_name_cbor_decoder = "aws_cbor_decoder";

static struct aws_cbor_decoder *s_cbor_decoder_from_capsule(PyObject *py_capsule) {
    return PyCapsule_GetPointer(py_capsule, s_capsule_name_cbor_decoder);
}
/* Runs when GC destroys the capsule */
static void s_cbor_decoder_capsule_destructor(PyObject *py_capsule) {
    struct aws_cbor_decoder *decoder = s_cbor_decoder_from_capsule(py_capsule);
    aws_cbor_decoder_release(decoder);
}

PyObject *aws_py_cbor_decoder_new(PyObject *self, PyObject *args) {
    (void)self;
    /* The python object will keep the src alive from python. */
    struct aws_byte_cursor src; /* s# */

    if (!PyArg_ParseTuple(args, "s#", &src.ptr, &src.len)) {
        return NULL;
    }

    struct aws_cbor_decoder *decoder = aws_cbor_decoder_new(aws_py_get_allocator(), &src);
    AWS_ASSERT(decoder != NULL);
    PyObject *py_capsule = PyCapsule_New(decoder, s_capsule_name_cbor_decoder, s_cbor_decoder_capsule_destructor);
    if (!py_capsule) {
        aws_cbor_decoder_release(decoder);
        return NULL;
    }

    return py_capsule;
}

#define S_DECODER_METHOD_START(decoder_func, out_val)                                                                  \
    (void)self;                                                                                                        \
    PyObject *py_capsule;                                                                                              \
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {                                                                   \
        return NULL;                                                                                                   \
    }                                                                                                                  \
    struct aws_cbor_decoder *decoder = s_cbor_decoder_from_capsule(py_capsule);                                        \
    if (!decoder) {                                                                                                    \
        return NULL;                                                                                                   \
    }                                                                                                                  \
    if (decoder_func(decoder, &out_val)) {                                                                             \
        return PyErr_AwsLastError();                                                                                   \
    }

PyObject *aws_py_cbor_decoder_peek_type(PyObject *self, PyObject *args) {
    enum aws_cbor_element_type out_type;
    S_DECODER_METHOD_START(aws_cbor_decode_peek_type, out_type);
    /* TODO: an convert from C type to the Python type */
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_decoder_get_remaining_bytes_len(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {
        return NULL;
    }
    struct aws_cbor_decoder *decoder = s_cbor_decoder_from_capsule(py_capsule);
    if (!decoder) {
        return NULL;
    }
    size_t remaining_len = aws_cbor_decoder_get_remaining_length(decoder);
    return PyLong_FromSize_t(remaining_len);
}

PyObject *aws_py_cbor_decoder_consume_next_element(PyObject *self, PyObject *args) {
    enum aws_cbor_element_type out_type;
    S_DECODER_METHOD_START(aws_cbor_decode_consume_next_element, out_type);
    /* TODO: an convert from C type to the Python type */
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_decoder_consume_next_data_item(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {
        return NULL;
    }
    struct aws_cbor_decoder *decoder = s_cbor_decoder_from_capsule(py_capsule);
    if (!decoder) {
        return NULL;
    }
    if (aws_cbor_decode_consume_next_data_item(decoder)) {
        return PyErr_AwsLastError();
    }
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_decoder_get_next_unsigned_int(PyObject *self, PyObject *args) {
    uint64_t out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_unsigned_val, out_val);
    return PyLong_FromUnsignedLongLong(out_val);
}

PyObject *aws_py_cbor_decoder_get_next_negative_int(PyObject *self, PyObject *args) {
    uint64_t out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_neg_val, out_val);
    return PyLong_FromUnsignedLongLong(out_val);
}

PyObject *aws_py_cbor_decoder_get_next_double(PyObject *self, PyObject *args) {
    double out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_double_val, out_val);
    return PyFloat_FromDouble(out_val);
}

PyObject *aws_py_cbor_decoder_get_next_bool(PyObject *self, PyObject *args) {
    bool out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_boolean_val, out_val);
    return PyBool_FromLong(out_val);
}

PyObject *aws_py_cbor_decoder_get_next_bytes(PyObject *self, PyObject *args) {
    struct aws_byte_cursor out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_bytes_val, out_val);
    return PyBytes_FromAwsByteCursor(&out_val);
}

PyObject *aws_py_cbor_decoder_get_next_str(PyObject *self, PyObject *args) {
    struct aws_byte_cursor out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_str_val, out_val);
    return PyUnicode_FromAwsByteCursor(&out_val);
}

PyObject *aws_py_cbor_decoder_get_next_array_start(PyObject *self, PyObject *args) {
    uint64_t out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_array_start, out_val);
    return PyLong_FromUnsignedLongLong(out_val);
}

PyObject *aws_py_cbor_decoder_get_next_map_start(PyObject *self, PyObject *args) {
    uint64_t out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_map_start, out_val);
    return PyLong_FromUnsignedLongLong(out_val);
}

PyObject *aws_py_cbor_decoder_get_next_tag_val(PyObject *self, PyObject *args) {
    uint64_t out_val;
    S_DECODER_METHOD_START(aws_cbor_decode_get_next_tag_val, out_val);
    return PyLong_FromUnsignedLongLong(out_val);
}