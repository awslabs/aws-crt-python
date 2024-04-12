#ifndef AWS_CRT_PYTHON_CBOR_H
#    define AWS_CRT_PYTHON_CBOR_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#    include "module.h"

/*******************************************************************************
 * ENCODE
 ******************************************************************************/

PyObject *aws_py_cbor_encoder_new(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_get_encoded_data(PyObject *self, PyObject *args);

PyObject *aws_py_cbor_encoder_encode_unsigned_int(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_encode_negative_int(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_encode_float(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_encode_bytes(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_encode_str(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_encode_array_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_encode_map_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_encode_tag(PyObject *self, PyObject *args);

/* Encode the types without value needed. The arg is the type to encode. */
PyObject *aws_py_cbor_encoder_encode_simple_types(PyObject *self, PyObject *args);

/*******************************************************************************
 * DECODE
 ******************************************************************************/

PyObject *aws_py_cbor_decoder_new(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_peek_type(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_remaining_bytes_len(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_consume_next_element(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_consume_next_data_item(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_unsigned_int(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_negative_int(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_double(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_bool(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_bytes(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_str(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_array_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_map_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_next_tag_val(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_CBOR_H */
       // PyObject *aws_py_(PyObject *self, PyObject *args);