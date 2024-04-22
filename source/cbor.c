/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "cbor.h"

#include <aws/common/cbor.h>

/*******************************************************************************
 * ENCODE
 ******************************************************************************/

struct encoder_binding {
    struct aws_cbor_encoder *native;

    /* Encoder has simple lifetime, no async/multi-thread allowed. */
    PyObject *self_py;
};

static const char *s_capsule_name_cbor_encoder = "aws_cbor_encoder";

static struct aws_cbor_encoder *s_cbor_encoder_from_capsule(PyObject *py_capsule) {
    struct encoder_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_cbor_encoder);
    if (!binding) {
        return NULL;
    }
    return binding->native;
}

/* Runs when GC destroys the capsule */
static void s_cbor_encoder_capsule_destructor(PyObject *py_capsule) {
    struct encoder_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_cbor_encoder);
    aws_cbor_encoder_release(binding->native);
    aws_mem_release(aws_py_get_allocator(), binding);
}

PyObject *aws_py_cbor_encoder_new(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_self;
    if (!PyArg_ParseTuple(args, "O", &py_self)) {
        return NULL;
    }

    struct encoder_binding *binding = aws_mem_calloc(aws_py_get_allocator(), 1, sizeof(struct encoder_binding));
    binding->native = aws_cbor_encoder_new(aws_py_get_allocator(), NULL);
    AWS_ASSERT(encoder != NULL);
    PyObject *py_capsule = PyCapsule_New(binding, s_capsule_name_cbor_encoder, s_cbor_encoder_capsule_destructor);
    if (!py_capsule) {
        aws_cbor_encoder_release(binding->native);
        aws_mem_release(aws_py_get_allocator(), binding);
        return NULL;
    }

    /* The binding and the py_object have the same life time */
    binding->self_py = py_self;
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

#define S_ENCODER_WRITE_PYOBJECT(ctype, py_conversion, field)                                                          \
    static PyObject *s_cbor_encoder_write_pyobject_as_##field(struct aws_cbor_encoder *encoder, PyObject *py_object) { \
        ctype data = py_conversion(py_object);                                                                         \
        if (PyErr_Occurred()) {                                                                                        \
            return NULL;                                                                                               \
        }                                                                                                              \
        aws_cbor_encoder_write_##field(encoder, data);                                                                 \
        Py_RETURN_NONE;                                                                                                \
    }

S_ENCODER_WRITE_PYOBJECT(uint64_t, PyLong_AsUnsignedLongLong, uint)
S_ENCODER_WRITE_PYOBJECT(uint64_t, PyLong_AsUnsignedLongLong, negint)
S_ENCODER_WRITE_PYOBJECT(double, PyFloat_AsDouble, double)
S_ENCODER_WRITE_PYOBJECT(struct aws_byte_cursor, aws_byte_cursor_from_pybytes, bytes)
S_ENCODER_WRITE_PYOBJECT(struct aws_byte_cursor, aws_byte_cursor_from_pyunicode, string)
S_ENCODER_WRITE_PYOBJECT(bool, PyObject_IsTrue, bool)

S_ENCODER_WRITE_PYOBJECT(uint64_t, PyLong_AsUnsignedLongLong, array_start)
S_ENCODER_WRITE_PYOBJECT(uint64_t, PyLong_AsUnsignedLongLong, map_start)
S_ENCODER_WRITE_PYOBJECT(uint64_t, PyLong_AsUnsignedLongLong, tag)

PyObject *aws_py_cbor_encoder_write_unsigned_int(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    return s_cbor_encoder_write_pyobject_as_uint(encoder, pylong);
}

PyObject *aws_py_cbor_encoder_write_negative_int(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    return s_cbor_encoder_write_pyobject_as_negint(encoder, pylong);
}

PyObject *aws_py_cbor_encoder_write_float(PyObject *self, PyObject *args) {
    PyObject *pyfloat;
    S_ENCODER_METHOD_START("O", &pyfloat);
    return s_cbor_encoder_write_pyobject_as_double(encoder, pyfloat);
}

PyObject *aws_py_cbor_encoder_write_bytes(PyObject *self, PyObject *args) {
    PyObject *py_bytes;
    S_ENCODER_METHOD_START("O", &py_bytes);
    return s_cbor_encoder_write_pyobject_as_bytes(encoder, py_bytes);
}

PyObject *aws_py_cbor_encoder_write_str(PyObject *self, PyObject *args) {
    PyObject *py_str;
    S_ENCODER_METHOD_START("O", &py_str);
    return s_cbor_encoder_write_pyobject_as_string(encoder, py_str);
}

PyObject *aws_py_cbor_encoder_write_array_start(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    return s_cbor_encoder_write_pyobject_as_array_start(encoder, pylong);
}

PyObject *aws_py_cbor_encoder_write_map_start(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    return s_cbor_encoder_write_pyobject_as_map_start(encoder, pylong);
}

PyObject *aws_py_cbor_encoder_write_tag(PyObject *self, PyObject *args) {
    PyObject *pylong;
    S_ENCODER_METHOD_START("O", &pylong);
    return s_cbor_encoder_write_pyobject_as_tag(encoder, pylong);
}

PyObject *aws_py_cbor_encoder_write_bool(PyObject *self, PyObject *args) {
    PyObject *pybool;
    S_ENCODER_METHOD_START("O", &pybool);
    return s_cbor_encoder_write_pyobject_as_bool(encoder, pybool);
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
    }
    Py_RETURN_NONE;
}

static PyObject *s_cbor_encoder_write_pyobject(struct encoder_binding *encoder_binding, PyObject *py_object);

static PyObject *s_cbor_encoder_write_pylong(struct encoder_binding *encoder_binding, PyObject *py_object) {
    long val;
    int overflow;

    val = PyLong_AsLongAndOverflow(py_object, &overflow);
    if (overflow == 0) {
        /* No overflow, just call into C */
        if (val >= 0) {
            aws_cbor_encoder_write_uint(encoder_binding->native, (uint64_t)val);
        } else {
            aws_cbor_encoder_write_negint(encoder_binding->native, -1 - val);
        }
    } else {
        /* TODO: handle it in C? */
        return PyObject_CallMethod(encoder_binding->self_py, "write_int", "(O)", py_object);
    }
    Py_RETURN_NONE;
}

static PyObject *s_cbor_encoder_write_pylist(struct encoder_binding *encoder_binding, PyObject *py_list) {
    Py_ssize_t size = PyList_Size(py_list);
    aws_cbor_encoder_write_array_start(encoder_binding->native, (size_t)size);
    for (Py_ssize_t i = 0; i < size; i++) {
        PyObject *item = PyList_GetItem(py_list, i);
        if (!item) {
            return NULL;
        }
        s_cbor_encoder_write_pyobject(encoder_binding, item);
    }
    Py_RETURN_NONE;
}

static PyObject *s_cbor_encoder_write_pydict(struct encoder_binding *encoder_binding, PyObject *py_dict) {
    Py_ssize_t size = PyDict_Size(py_dict);
    aws_cbor_encoder_write_map_start(encoder_binding->native, (size_t)size);
    PyObject *key = NULL;
    PyObject *value = NULL;
    Py_ssize_t pos = 0;

    while (PyDict_Next(py_dict, &pos, &key, &value)) {
        s_cbor_encoder_write_pyobject(encoder_binding, key);
        s_cbor_encoder_write_pyobject(encoder_binding, value);
    }
    Py_RETURN_NONE;
}

static PyObject *s_cbor_encoder_write_pyobject(struct encoder_binding *encoder_binding, PyObject *py_object) {

    /**
     * TODO: timestamp <-> datetime?? Decimal fraction <-> decimal??
     */
    if (PyLong_CheckExact(py_object)) {
        /* Call to Python to write pylong, as it's too complicate */
        return s_cbor_encoder_write_pylong(encoder_binding, py_object);
    } else if (PyFloat_CheckExact(py_object)) {
        return s_cbor_encoder_write_pyobject_as_double(encoder_binding->native, py_object);
    } else if (PyBool_Check(py_object)) {
        return s_cbor_encoder_write_pyobject_as_bool(encoder_binding->native, py_object);
    } else if (PyBytes_CheckExact(py_object)) {
        return s_cbor_encoder_write_pyobject_as_bytes(encoder_binding->native, py_object);
    } else if (PyUnicode_CheckExact(py_object)) {
        return s_cbor_encoder_write_pyobject_as_string(encoder_binding->native, py_object);
    } else if (PyList_CheckExact(py_object)) {
        /* Write py_list */
        return s_cbor_encoder_write_pylist(encoder_binding, py_object);
    } else if (PyDict_CheckExact(py_object)) {
        /* Write py_dict */
        return s_cbor_encoder_write_pydict(encoder_binding, py_object);
    } else if (py_object == Py_None) {
        aws_cbor_encoder_write_null(encoder_binding->native);
    } else {
        PyErr_Format(PyExc_ValueError, "Not supported type %R", (PyObject *)Py_TYPE(py_object));
    }

    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_encoder_write_py_list(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_object;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "OO", &py_capsule, &py_object)) {
        return NULL;
    }
    struct encoder_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_cbor_encoder);
    if (!binding) {
        return NULL;
    }
    return s_cbor_encoder_write_pylist(binding, py_object);
}

PyObject *aws_py_cbor_encoder_write_py_dict(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_object;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "OO", &py_capsule, &py_object)) {
        return NULL;
    }
    struct encoder_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_cbor_encoder);
    if (!binding) {
        return NULL;
    }
    return s_cbor_encoder_write_pydict(binding, py_object);
}

PyObject *aws_py_cbor_encoder_write_data_item(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *py_object;
    PyObject *py_capsule;
    if (!PyArg_ParseTuple(args, "OO", &py_capsule, &py_object)) {
        return NULL;
    }
    struct encoder_binding *binding = PyCapsule_GetPointer(py_capsule, s_capsule_name_cbor_encoder);
    if (!binding) {
        return NULL;
    }
    return s_cbor_encoder_write_pyobject(binding, py_object);
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
    Py_RETURN_NONE;
}

PyObject *aws_py_cbor_decoder_consume_next_data_item(PyObject *self, PyObject *args) {
    S_GET_DECODER();
    if (aws_cbor_decoder_consume_next_data_item(decoder)) {
        return PyErr_AwsLastError();
    }
    Py_RETURN_NONE;
}

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
 * helper to convert next data item to py_list
 */
static PyObject *s_cbor_decoder_pop_next_data_item_to_py_list(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = AWS_CBOR_TYPE_MAX;
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
 * helper to convert next data item to py_dict
 */
static PyObject *s_cbor_decoder_pop_next_data_item_to_py_dict(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = AWS_CBOR_TYPE_MAX;
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
 * helper to get the next inf byte
 */
static PyObject *s_cbor_decoder_pop_next_inf_bytes_to_py_bytes(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = AWS_CBOR_TYPE_MAX;
    if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
        return PyErr_AwsLastError();
    }
    if (out_type != AWS_CBOR_TYPE_INF_BYTESTRING_START) {
        aws_raise_error(AWS_ERROR_CBOR_UNEXPECTED_TYPE);
        return PyErr_AwsLastError();
    }
    /* consume the bytes start element */
    aws_cbor_decoder_consume_next_element(decoder, NULL);
    if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
        return PyErr_AwsLastError();
    }
    /* Empty bytes */
    PyObject *result = PyBytes_FromStringAndSize(NULL, 0);
    while (out_type != AWS_CBOR_TYPE_BREAK) {
        PyObject *next_part = s_cbor_decoder_pop_next_bytes_val_to_pyobject(decoder);
        if (!next_part) {
            Py_DECREF(result);
            return NULL;
        }
        /* The reference to the old value of bytes will be stolen and next_part will be del. */
        PyBytes_ConcatAndDel(&result, next_part);
        if (!result) {
            return NULL;
        }
        if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
            return PyErr_AwsLastError();
        }
    }
    return result;
}

/**
 * helper to get the next inf string
 */
static PyObject *s_cbor_decoder_pop_next_inf_string_to_py_str(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = AWS_CBOR_TYPE_MAX;
    if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
        return PyErr_AwsLastError();
    }
    if (out_type != AWS_CBOR_TYPE_INF_STRING_START) {
        aws_raise_error(AWS_ERROR_CBOR_UNEXPECTED_TYPE);
        return PyErr_AwsLastError();
    }
    /* consume the bytes start element */
    aws_cbor_decoder_consume_next_element(decoder, NULL);
    if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
        return PyErr_AwsLastError();
    }
    /* Empty string */
    PyObject *result = PyUnicode_FromStringAndSize(NULL, 0);
    while (out_type != AWS_CBOR_TYPE_BREAK) {
        PyObject *next_part = s_cbor_decoder_pop_next_str_val_to_pyobject(decoder);
        if (!next_part) {
            Py_DECREF(result);
            return NULL;
        }
        /* Returns a new reference and keep the arguments unchanged. */
        PyObject *concat_val = PyUnicode_Concat(result, next_part);
        Py_DECREF(result);
        Py_DECREF(next_part);
        if (!concat_val) {
            return NULL;
        }
        result = concat_val;
        if (aws_cbor_decoder_peek_type(decoder, &out_type)) {
            return PyErr_AwsLastError();
        }
    }
    return result;
}

/**
 * Generic helper to convert a cbor encoded data to PyObject
 */
static PyObject *s_cbor_decoder_pop_next_tag_to_pyobject(struct aws_cbor_decoder *decoder) {
    uint64_t out_tag_val = 0;
    if (aws_cbor_decoder_pop_next_tag_val(decoder, &out_tag_val)) {
        return PyErr_AwsLastError();
    }
    /* TODO: implement those tags */
    switch (out_tag_val) {
        case AWS_CBOR_TAG_EPOCH_TIME:
        case AWS_CBOR_TAG_UNSIGNED_BIGNUM:
        case AWS_CBOR_TAG_NEGATIVE_BIGNUM:
        case AWS_CBOR_TAG_DECIMAL_FRACTION:
        default:
            PyErr_Format(PyExc_ValueError, "Unsupported tag value: %" PRIu64 ".", out_tag_val);
            return NULL;
    }
    Py_RETURN_NONE;
}

/**
 * Generic helper to convert a cbor encoded data to PyObject
 */
static PyObject *s_cbor_decoder_pop_next_data_item_to_pyobject(struct aws_cbor_decoder *decoder) {
    enum aws_cbor_element_type out_type = AWS_CBOR_TYPE_MAX;
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
            /* fall through */
        case AWS_CBOR_TYPE_UNDEFINE:
            aws_cbor_decoder_consume_next_element(decoder, NULL);
            Py_RETURN_NONE;
        case AWS_CBOR_TYPE_MAP_START:
            /* fall through */
        case AWS_CBOR_TYPE_INF_MAP_START:
            return s_cbor_decoder_pop_next_data_item_to_py_dict(decoder);
        case AWS_CBOR_TYPE_ARRAY_START:
            /* fall through */
        case AWS_CBOR_TYPE_INF_ARRAY_START:
            return s_cbor_decoder_pop_next_data_item_to_py_list(decoder);
        case AWS_CBOR_TYPE_INF_BYTESTRING_START:
            return s_cbor_decoder_pop_next_inf_bytes_to_py_bytes(decoder);
        case AWS_CBOR_TYPE_INF_STRING_START:
            return s_cbor_decoder_pop_next_inf_string_to_py_str(decoder);
        case AWS_CBOR_TYPE_TAG:
            return s_cbor_decoder_pop_next_tag_to_pyobject(decoder);
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
