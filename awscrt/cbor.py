# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt

from awscrt import NativeResource
from enum import IntEnum
from typing import Any


class AwsCborElementType(IntEnum):
    Int = 0
    Float = 1
    String = 2
    Map = 3
    Array = 4
    NULL = 5


class AwsCborEncoder(NativeResource):
    """ Encoder for CBOR """

    def __init__(self):
        super().__init__()
        self._binding = _awscrt.cbor_encoder_new()

    def get_encoded_data(self) -> bytes:
        return _awscrt.cbor_encoder_get_encoded_data(self._binding)

    def write_int(self, val: int):
        """Add int to encode, -2^64 to 2^64 inclusive. Otherwise, overflow will be raised.

        Args:
            val (int): _description_

        Returns:
            _type_: _description_
        """
        if val < -2**64 or val > 2**64:
            raise OverflowError(f"{val} is overflowed to be encoded into cbor integers")

        if val >= 0:
            return _awscrt.cbor_encoder_write_unsigned_int(self._binding, val)
        else:
            return _awscrt.cbor_encoder_write_negative_int(self._binding, -1 - val)

    def write_float(self, val: float):
        """Adding a "double" to encode
            Rely on `PyFloat_AsDouble()` for error checking.
        Args:
            val (float): _description_
        """
        return _awscrt.cbor_encoder_write_float(self._binding, val)

    def write_bytes(self, val: bytes):
        return _awscrt.cbor_encoder_write_bytes(self._binding, val)

    def write_string(self, val: str):
        return _awscrt.cbor_encoder_write_str(self._binding, val)

    def write_array_start(self, number_entries: int):
        """Add a start of array element, with the `number_entries`
            for the cbor data items to be included in the array.
            `number_entries` should 0 to 2^64 inclusive.
            Otherwise, overflow will be raised.

        Args:
            number_entries (int): _description_

        Returns:
            _type_: _description_
        """
        if number_entries < 0 or number_entries > 2**64:
            raise OverflowError()

        return _awscrt.cbor_encoder_write_array_start(self._binding, number_entries)

    def write_map_start(self, number_entries: int):
        """Add a start of map element, with the `number_entries`
            for the number of pair of cbor data items to be included in the map.
            `number_entries` should 0 to 2^64 inclusive.
            Otherwise, overflow will be raised.

        Args:
            number_entries (int): _description_

        Returns:
            _type_: _description_
        """
        if number_entries < 0 or number_entries > 2**64:
            raise ValueError()

        return _awscrt.cbor_encoder_write_map_start(self._binding, number_entries)

    def write_tag(self, tag_number: int):
        if tag_number < 0 or tag_number > 2**64:
            raise ValueError()

        return _awscrt.cbor_encoder_write_tag(self._binding, tag_number)

    def write_null(self):
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborElementType.NULL)


class AwsCborDecoder(NativeResource):
    """ Decoder for CBOR """

    def __init__(self, src: bytes):
        super().__init__()
        self._src = src
        self._binding = _awscrt.cbor_decoder_new(src)

    def peek_next_type(self) -> AwsCborElementType:
        return _awscrt.cbor_decoder_peek_type(self._binding)

    def get_remaining_bytes_len(self) -> int:
        return _awscrt.cbor_decoder_get_remaining_bytes_len(self._binding)

    def consume_next_element(self):
        return _awscrt.cbor_decoder_consume_next_element(self._binding)

    def consume_next_data_item(self):
        return _awscrt.cbor_decoder_consume_next_data_item(self._binding)

    def get_next_unsigned_int(self) -> int:
        return _awscrt.cbor_decoder_get_next_unsigned_int(self._binding)

    def get_next_negative_int(self) -> int:
        val = _awscrt.cbor_decoder_get_next_negative_int(self._binding)
        return -1 - val

    def get_next_double(self) -> float:
        return _awscrt.cbor_decoder_get_next_double(self._binding)

    def get_next_bool(self) -> bool:
        return _awscrt.cbor_decoder_get_next_bool(self._binding)

    def get_next_bytes(self) -> bytes:
        return _awscrt.cbor_decoder_get_next_bytes(self._binding)

    def get_next_str(self) -> str:
        return _awscrt.cbor_decoder_get_next_str(self._binding)

    def get_next_array_start(self) -> int:
        return _awscrt.cbor_decoder_get_next_array_start(self._binding)

    def get_next_map_start(self) -> int:
        return _awscrt.cbor_decoder_get_next_map_start(self._binding)

    def get_next_tag_val(self) -> int:
        return _awscrt.cbor_decoder_get_next_tag_val(self._binding)
