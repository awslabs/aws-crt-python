# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt

from awscrt import NativeResource
from enum import IntEnum
from typing import Union, Any


class AwsCborType(IntEnum):
    # Corresponding to `enum aws_cbor_type` in aws/common/cbor.h
    Unknown = 0
    UnsignedInt = 1
    NegativeInt = 2
    Float = 3
    Bytes = 4
    Text = 5
    ArrayStart = 6
    MapStart = 7
    Tag = 8
    Bool = 9
    Null = 10
    Undefined = 11
    Break = 12
    IndefBytes = 13
    IndefStr = 14
    IndefArray = 15
    IndefMap = 16


class AwsCborEncoder(NativeResource):
    """ Encoder for CBOR """

    def __init__(self):
        super().__init__()
        self._binding = _awscrt.cbor_encoder_new(self)

    def get_encoded_data(self) -> bytes:
        """Return the current encoded data as bytes

        Returns:
            bytes: The encoded data currently
        """
        return _awscrt.cbor_encoder_get_encoded_data(self._binding)

    def write_int(self, val: int):
        # TODO: maybe not support bignum for now. Not needed?
        """Write an int as cbor formatted,
            val less than -2^64 will be encoded as Negative bignum for CBOR
            val between -2^64 to -1, inclusive, will be encode as negative integer for CBOR
            val between 0 to 2^64 - 1, inclusive, will be encoded as unsigned integer for CBOR
            val greater than 2^64 - 1 will be encoded as Unsigned bignum for CBOR

        Args:
            val (int): value to be encoded and written to the encoded data.
        """
        assert isinstance(val, int)
        val_to_encode = val
        if val < 0:
            # For negative value, the value to encode is -1 - val.
            val_to_encode = -1 - val
        bit_len = val_to_encode.bit_length()
        if bit_len > 64:
            # Bignum
            bytes_len = bit_len // 8
            if bit_len % 8 > 0:
                bytes_len += 1
            bytes_val = val_to_encode.to_bytes(bytes_len, "big")
            if val < 0:
                self.write_tag(AwsCborTags.NegativeBigNum)  # tag for negative bignum
            else:
                self.write_tag(AwsCborTags.UnsignedBigNum)  # tag for unsigned bignum
            return self.write_bytes(bytes_val)

        if val >= 0:
            return _awscrt.cbor_encoder_write_unsigned_int(self._binding, val_to_encode)
        else:
            return _awscrt.cbor_encoder_write_negative_int(self._binding, val_to_encode)

    def write_float(self, val: float):
        """Write a double as cbor formatted
            If the val can be convert the int without loss of precision,
            it will be converted to int to be written to as cbor formatted.

        Args:
            val (float): value to be encoded and written to the encoded data.
        """
        assert isinstance(val, float)
        # Floating point numbers are usually implemented using double in C
        return _awscrt.cbor_encoder_write_float(self._binding, val)

    def write_bytes(self, val: bytes):
        """Write bytes as cbor formatted

        Args:
            val (bytes): value to be encoded and written to the encoded data.
        """
        return _awscrt.cbor_encoder_write_bytes(self._binding, val)

    def write_text(self, val: str):
        """Write text as cbor formatted

        Args:
            val (str): value to be encoded and written to the encoded data.
        """
        return _awscrt.cbor_encoder_write_text(self._binding, val)

    def write_array_start(self, number_entries: int):
        """Add a start of array element.
            A legistic with the `number_entries`
            for the cbor data items to be included in the array.
            `number_entries` should 0 to 2^64 inclusive.
            Otherwise, overflow will be raised.

        Args:
            number_entries (int): number of entries in the array to be written
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
            number_entries (int): number of entries in the map to be written
        """
        if number_entries < 0 or number_entries > 2**64:
            raise ValueError()

        return _awscrt.cbor_encoder_write_map_start(self._binding, number_entries)

    def write_tag(self, tag_number: int):
        if tag_number < 0 or tag_number > 2**64:
            raise ValueError()

        return _awscrt.cbor_encoder_write_tag(self._binding, tag_number)

    def write_null(self):
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.Null)

    def write_bool(self, val: bool):
        return _awscrt.cbor_encoder_write_bool(self._binding, val)

    def write_list(self, val: list):
        return _awscrt.cbor_encoder_write_py_list(self._binding, val)

    def write_dict(self, val: dict):
        return _awscrt.cbor_encoder_write_py_dict(self._binding, val)

    def write_data_item(self, data_item: Any):
        """Generic API to write any type of an data_item as cbor formatted.
        TODO: timestamp <-> datetime?? Decimal fraction <-> decimal??

        Args:
            data_item (Any): any type of data_item. If the type is not supported to be converted to cbor format, ValueError will be raised.
        """
        return _awscrt.cbor_encoder_write_data_item(self._binding, data_item)


class AwsCborDecoder(NativeResource):
    """ Decoder for CBOR """

    def __init__(self, src: bytes):
        super().__init__()
        self._src = src
        self._binding = _awscrt.cbor_decoder_new(src)

    def peek_next_type(self) -> AwsCborType:
        return AwsCborType(_awscrt.cbor_decoder_peek_type(self._binding))

    def get_remaining_bytes_len(self) -> int:
        return _awscrt.cbor_decoder_get_remaining_bytes_len(self._binding)

    def consume_next_element(self):
        return _awscrt.cbor_decoder_consume_next_element(self._binding)

    def consume_next_data_item(self):
        return _awscrt.cbor_decoder_consume_next_data_item(self._binding)

    def pop_next_unsigned_int(self) -> int:
        return _awscrt.cbor_decoder_pop_next_unsigned_int(self._binding)

    def pop_next_negative_int(self) -> int:
        val = _awscrt.cbor_decoder_pop_next_negative_int(self._binding)
        return -1 - val

    def pop_next_double(self) -> float:
        return _awscrt.cbor_decoder_pop_next_float(self._binding)

    def pop_next_bool(self) -> bool:
        return _awscrt.cbor_decoder_pop_next_bool(self._binding)

    def pop_next_bytes(self) -> bytes:
        return _awscrt.cbor_decoder_pop_next_bytes(self._binding)

    def pop_next_text(self) -> str:
        return _awscrt.cbor_decoder_pop_next_text(self._binding)

    def pop_next_array_start(self) -> int:
        return _awscrt.cbor_decoder_pop_next_array_start(self._binding)

    def pop_next_map_start(self) -> int:
        return _awscrt.cbor_decoder_pop_next_map_start(self._binding)

    def pop_next_tag_val(self) -> int:
        return _awscrt.cbor_decoder_pop_next_tag_val(self._binding)

    def pop_next_list(self) -> list:
        return _awscrt.cbor_decoder_pop_next_py_list(self._binding)

    def pop_next_map(self) -> dict:
        return _awscrt.cbor_decoder_pop_next_py_dict(self._binding)

    def pop_next_data_item(self) -> Any:
        return _awscrt.cbor_decoder_pop_next_data_item(self._binding)
