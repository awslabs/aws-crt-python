#ifndef AWS_CRT_PYTHON_CBOR_H
#define AWS_CRT_PYTHON_CBOR_H
/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include "module.h"

/*******************************************************************************
 * ENCODE
 ******************************************************************************/

PyObject *aws_py_cbor_encoder_new(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_get_encoded_data(PyObject *self, PyObject *args);

PyObject *aws_py_cbor_encoder_write_uint(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_negint(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_float(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_bytes(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_text(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_array_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_map_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_tag(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_bool(PyObject *self, PyObject *args);

/* Encode the types without value needed. The arg is the type to encode. */
PyObject *aws_py_cbor_encoder_write_simple_types(PyObject *self, PyObject *args);

PyObject *aws_py_cbor_encoder_write_py_list(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_py_dict(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_data_item(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_encoder_write_data_item_shaped(PyObject *self, PyObject *args);

/*******************************************************************************
 * DECODE
 ******************************************************************************/

PyObject *aws_py_cbor_decoder_new(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_peek_type(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_get_remaining_bytes_len(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_consume_next_element(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_consume_next_data_item(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_unsigned_int(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_negative_int(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_float(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_boolean(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_bytes(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_text(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_array_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_map_start(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_tag(PyObject *self, PyObject *args);

PyObject *aws_py_cbor_decoder_pop_next_py_list(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_py_dict(PyObject *self, PyObject *args);
PyObject *aws_py_cbor_decoder_pop_next_data_item(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_CBOR_H */
