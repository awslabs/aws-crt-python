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

    struct aws_cbor_encoder *encoder = aws_cbor_encoder_new(aws_py_get_allocator(), NULL);
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

PyObject *aws_py_cbor_encoder_write_unsigned_int(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    if (PyErr_Occurred()) {
        PyErr_SetString(PyExc_ValueError, "AwsCborEncoder.write_int is not a valid int to encode");
        return NULL;
    }
    aws_cbor_encoder_write_uint(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_negative_int(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    if (PyErr_Occurred()) {
        PyErr_SetString(PyExc_ValueError, "AwsCborEncoder.write_int is not a valid int to encode");
        return NULL;
    }
    aws_cbor_encoder_write_negint(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_float(PyObject *self, PyObject *args) {
    PyObject *pyfloat;
    S_ENCODER_METHOD_START("O", &pyfloat);
    double data = PyFloat_AsDouble(pyfloat);
    /* Rely on the python convert to check the pyfloat is able to convert to double. */
    if (PyErr_Occurred()) {
        PyErr_SetString(PyExc_ValueError, "AwsCborEncoder.write_float is not a valid double to encode");
        return NULL;
    }
    aws_cbor_encoder_write_double(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_bytes(PyObject *self, PyObject *args) {
    struct aws_byte_cursor bytes_data;
    S_ENCODER_METHOD_START("y#", &bytes_data.ptr, &bytes_data.len);
    aws_cbor_encoder_write_bytes(encoder, bytes_data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_str(PyObject *self, PyObject *args) {
    struct aws_byte_cursor str_data;
    S_ENCODER_METHOD_START("s#", &str_data.ptr, &str_data.len);
    aws_cbor_encoder_write_string(encoder, str_data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_array_start(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    if (PyErr_Occurred()) {
        PyErr_SetString(PyExc_ValueError, "AwsCborEncoder.write_array_start is not a valid int to encode");
        return NULL;
    }
    aws_cbor_encoder_write_array_start(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_map_start(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    if (PyErr_Occurred()) {
        PyErr_SetString(PyExc_ValueError, "AwsCborEncoder.write_map_start is not a valid int to encode");
        return NULL;
    }
    aws_cbor_encoder_write_map_start(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_tag(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    uint64_t data = PyLong_AsUnsignedLongLong(pylong);
    /* The python code has already checked the value */
    if (PyErr_Occurred()) {
        PyErr_SetString(PyExc_ValueError, "AwsCborEncoder.write_tag is not a valid int to encode");
        return NULL;
    }
    aws_cbor_encoder_write_tag(encoder, data);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_bool(PyObject *self, PyObject *args) {
    int bool_val;
    S_ENCODER_METHOD_START("p", &bool_val);
    aws_cbor_encoder_write_bool(encoder, bool_val);
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_simple_types(PyObject *self, PyObject *args) {
    Py_ssize_t type_enum;
    S_ENCODER_METHOD_START("n", &type_enum);
    switch (type_enum) {
        case AWS_CBOR_TYPE_NULL:
            aws_cbor_encoder_write_null(encoder);
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

#define S_GET_DECODER()                                                                                                \
    (void)self;                                                                                                        \
    PyObject *py_capsule;                                                                                              \
    if (!PyArg_ParseTuple(args, "O", &py_capsule)) {                                                                   \
        return NULL;                                                                                                   \
    }                                                                                                                  \
    struct aws_cbor_decoder *decoder = s_cbor_decoder_from_capsule(py_capsule);                                        \
    if (!decoder) {                                                                                                    \
        return NULL;                                                                                                   \
    }

#define S_DECODER_METHOD_START(decoder_func, out_val)                                                                  \
    S_GET_DECODER()                                                                                                    \
    if (decoder_func(decoder, &out_val)) {                                                                             \
        return PyErr_AwsLastError();                                                                                   \
    }

#define S_POP_NEXT_TO_PYOBJECT(ctype, field, py_conversion)                                                            \
    static PyObject *s_cbor_decoder_pop_next_##field##_to_pyobject(struct aws_cbor_decoder *decoder) {                 \
        ctype out_val;                                                                                                 \
        if (aws_cbor_decoder_pop_next_##field(decoder, &out_val)) {                                                    \
            return PyErr_AwsLastError();                                                                               \
        }                                                                                                              \
        return py_conversion(out_val);                                                                                 \
    }

#define S_POP_NEXT_TO_PYOBJECT_CURSOR(field, py_conversion)                                                            \
    static PyObject *s_cbor_decoder_pop_next_##field##_to_pyobject(struct aws_cbor_decoder *decoder) {                 \
        struct aws_byte_cursor out_val;                                                                                \
        if (aws_cbor_decoder_pop_next_##field(decoder, &out_val)) {                                                    \
            return PyErr_AwsLastError();                                                                               \
        }                                                                                                              \
        return py_conversion(&out_val);                                                                                \
    }

PyObject *aws_py_cbor_decoder_peek_type(PyObject *self, PyObject *args) {
    enum aws_cbor_element_type out_type;
    S_DECODER_METHOD_START(aws_cbor_decoder_peek_type, out_type);
    return PyLong_FromSize_t(out_type);
}

PyObject *aws_py_cbor_decoder_get_remaining_bytes_len(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    size_t remaining_len = aws_cbor_decoder_get_remaining_length(decoder);
    return PyLong_FromSize_t(remaining_len);
}

PyObject *aws_py_cbor_decoder_consume_next_element(PyObject *self, PyObject *args) {
    enum aws_cbor_element_type out_type;
    S_DECODER_METHOD_START(aws_cbor_decoder_consume_next_element, out_type);
    /* TODO: an convert from C type to the Python type */
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_decoder_consume_next_data_item(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    if (aws_cbor_decoder_consume_next_data_item(decoder)) {
        return PyErr_AwsLastError();
    }
    Py_RETURN_NONE;
}

// static PyObject *s_decode(struct aws_cbor_decoder *decoder) {}

S_POP_NEXT_TO_PYOBJECT(uint64_t, unsigned_val, PyLong_FromUnsignedLongLong)
S_POP_NEXT_TO_PYOBJECT(uint64_t, neg_val, PyLong_FromUnsignedLongLong)
S_POP_NEXT_TO_PYOBJECT(double, double_val, PyFloat_FromDouble)
S_POP_NEXT_TO_PYOBJECT(bool, boolean_val, PyBool_FromLong)
S_POP_NEXT_TO_PYOBJECT_CURSOR(bytes_val, PyBytes_FromAwsByteCursor)
S_POP_NEXT_TO_PYOBJECT_CURSOR(str_val, PyUnicode_FromAwsByteCursor)
S_POP_NEXT_TO_PYOBJECT(uint64_t, array_start, PyLong_FromUnsignedLongLong)
S_POP_NEXT_TO_PYOBJECT(uint64_t, map_start, PyLong_FromUnsignedLongLong)
S_POP_NEXT_TO_PYOBJECT(uint64_t, tag_val, PyLong_FromUnsignedLongLong)

static PyObject *s_cbor_decoder_pop_next_data_item_to_pyobject(struct aws_cbor_decoder *decoder);

/**
 * Generic helper to convert next data item to py_list
 */
static PyObject *s_cbor_decoder_pop_next_data_item_to_py_list(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = 0;
    if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
        return PyErr_AwsLastError();
    }
    PyObject *array = NULL;
    PyObject *item = NULL;
    switch (out_type) {
        case AWS_CBOR_TYPE_ARRAY_START: {
            uint64_t num_array_item;
            aws_cbor_decoder_pop_next_array_start(decoder, &num_array_item);
            if (num_array_item > PY_SSIZE_T_MAX) {
                PyErr_SetString(PyExc_OverflowError, "number of array is too large to fit.");
                return NULL;
            }
            array = PyList_New((Py_ssize_t)num_array_item);
            if (!array) {
                return NULL;
            }
            for (size_t i = 0; i < num_array_item; ++i) {
                item = s_cbor_decoder_pop_next_data_item_to_pyobject(decoder);
                if (!item) {
                    goto error;
                }
                PyList_SetItem(array, i, item); /* Steals reference to item */
            }
            return array;
        }
        case AWS_CBOR_TYPE_INF_ARRAY_START: {
            array = PyList_New(0);
            if (!array) {
                return NULL;
            }
            /* Consume the inf array start */
            aws_cbor_decoder_consume_next_element(decoder, NULL /*consumed_type*/);
            aws_cbor_decoder_peek_type(decoder, &out_type);
            while (out_type != AWS_CBOR_TYPE_BREAK) {
                item = s_cbor_decoder_pop_next_data_item_to_pyobject(decoder);
                if (!item) {
                    goto error;
                }
                if (PyList_Append(array, item) == -1) {
                    goto error;
                }
                /* Append will not steal the reference, deref here. */
                Py_DECREF(item);
                if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
                    PyErr_AwsLastError();
                    goto error;
                }
            }
            return array;
        }
        default:
            aws_raise_error(AWS_ERROR_CBOR_UNEXPECTED_TYPE);
            return PyErr_AwsLastError();
    }
error:
    if (array) {
        Py_DECREF(array);
    }
    return NULL;
}

/**
 * Generic helper to convert next data item to py_dict
 */
static PyObject *s_cbor_decoder_pop_next_data_item_to_py_dict(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = 0;
    if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
        return PyErr_AwsLastError();
    }
    PyObject *dict = NULL;
    PyObject *key = NULL;
    PyObject *value = NULL;
    switch (out_type) {
        case AWS_CBOR_TYPE_MAP_START: {
            uint64_t num_item;
            aws_cbor_decoder_pop_next_map_start(decoder, &num_item);
            if (num_item > PY_SSIZE_T_MAX) {
                PyErr_SetString(PyExc_OverflowError, "number of dict is too large to fit.");
                return NULL;
            }
            dict = PyDict_New();
            if (!dict) {
                return NULL;
            }
            for (size_t i = 0; i < num_item; ++i) {
                key = s_cbor_decoder_pop_next_data_item_to_pyobject(decoder);
                value = s_cbor_decoder_pop_next_data_item_to_pyobject(decoder);
                if (!key || !value) {
                    goto error;
                }
                if (PyDict_SetItem(dict, key, value) == -1) {
                    goto error;
                }
                Py_DECREF(key);
                Py_DECREF(value);
            }
            return dict;
        }
        case AWS_CBOR_TYPE_INF_MAP_START: {
            dict = PyDict_New();
            if (!dict) {
                return NULL;
            }
            /* Consume the inf array start */
            aws_cbor_decoder_consume_next_element(decoder, NULL /*consumed_type*/);
            aws_cbor_decoder_peek_type(decoder, &out_type);
            while (out_type != AWS_CBOR_TYPE_BREAK) {
                key = s_cbor_decoder_pop_next_data_item_to_pyobject(decoder);
                value = s_cbor_decoder_pop_next_data_item_to_pyobject(decoder);
                if (!key || !value) {
                    goto error;
                }
                if (PyDict_SetItem(dict, key, value) == -1) {
                    goto error;
                }
                Py_DECREF(key);
                Py_DECREF(value);
                if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
                    PyErr_AwsLastError();
                    goto error;
                }
            }
            return dict;
        }
        default:
            aws_raise_error(AWS_ERROR_CBOR_UNEXPECTED_TYPE);
            return PyErr_AwsLastError();
    }
error:
    if (dict) {
        Py_DECREF(dict);
    }
    if (key) {
        Py_DECREF(key);
    }
    if (value) {
        Py_DECREF(value);
    }
    return NULL;
}

/**
 * Generic helper to convert a cbor encoded data to PyObject
 */
static PyObject *s_cbor_decoder_pop_next_data_item_to_pyobject(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = 0;
    if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
        return PyErr_AwsLastError();
    }
    switch (out_type) {
        case AWS_CBOR_TYPE_UINT:
            return s_cbor_decoder_pop_next_unsigned_val_to_pyobject(decoder);
        case AWS_CBOR_TYPE_NEGINT: {
            /* The value from native code is -1 - val. */
            PyObject *minus_one = PyLong_FromLong(-1);
            if (!minus_one) {
                return NULL;
            }
            PyObject *val = s_cbor_decoder_pop_next_neg_val_to_pyobject(decoder);
            if (!val) {
                Py_DECREF(minus_one);
                return NULL;
            }
            /* Get  */
            PyObject *ret_val = PyNumber_Subtract(minus_one, val);
            Py_DECREF(minus_one);
            Py_DECREF(val);
            return ret_val;
        }
        case AWS_CBOR_TYPE_DOUBLE:
            return s_cbor_decoder_pop_next_double_val_to_pyobject(decoder);
        case AWS_CBOR_TYPE_BYTESTRING:
            return s_cbor_decoder_pop_next_bytes_val_to_pyobject(decoder);
        case AWS_CBOR_TYPE_STRING:
            return s_cbor_decoder_pop_next_str_val_to_pyobject(decoder);
        case AWS_CBOR_TYPE_BOOL:
            return s_cbor_decoder_pop_next_boolean_val_to_pyobject(decoder);
        case AWS_CBOR_TYPE_NULL:
        case AWS_CBOR_TYPE_UNDEFINE:
            aws_cbor_decoder_consume_next_element(decoder, NULL);
            Py_RETURN_NONE;
        case AWS_CBOR_TYPE_MAP_START:
        case AWS_CBOR_TYPE_INF_MAP_START:
            return s_cbor_decoder_pop_next_data_item_to_py_dict(decoder);
        case AWS_CBOR_TYPE_ARRAY_START:
        case AWS_CBOR_TYPE_INF_ARRAY_START:
            return s_cbor_decoder_pop_next_data_item_to_py_list(decoder);
        case AWS_CBOR_TYPE_INF_BYTESTRING_START:
        case AWS_CBOR_TYPE_INF_STRING_START:
        case AWS_CBOR_TYPE_TAG:
            /* TODO: handle those case */
        default:
            aws_raise_error(AWS_ERROR_CBOR_UNEXPECTED_TYPE);
            return PyErr_AwsLastError();
    }
    return NULL;
}

/*********************************** BINDINGS ***********************************************/

PyObject *aws_py_cbor_decoder_pop_next_unsigned_int(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_unsigned_val_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_negative_int(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_neg_val_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_double(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_double_val_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_bool(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_boolean_val_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_bytes(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_bytes_val_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_str(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_str_val_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_array_start(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_array_start_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_map_start(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_map_start_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_tag_val(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_tag_val_to_pyobject(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_py_list(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_data_item_to_py_list(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_py_dict(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_data_item_to_py_dict(decoder);
}

PyObject *aws_py_cbor_decoder_pop_next_data_item(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    return s_cbor_decoder_pop_next_data_item_to_pyobject(decoder);
}
