# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt

from awscrt import NativeResource
from enum import IntEnum
from typing import Union, Any


class AwsCborElementType(IntEnum):
    # Corresponding to `enum aws_cbor_element_type` in aws/common/cbor.h
    UnsignedInt = 0
    NegativeInt = 1
    Float = 2
    Bytes = 3
    String = 4
    ArrayStart = 5
    MapStart = 6
    Tag = 7
    Bool = 8
    Null = 9
    Undefined = 10
    Break = 11
    InfBytes = 12
    InfStr = 13
    InfArray = 14
    InfMap = 15


class AwsCborTags(IntEnum):
    # Corresponding to `enum aws_cbor_tags` in aws/common/cbor.h
    StandardTime = 0
    EpochTime = 1
    UnsignedBigNum = 2
    NegativeBigNum = 3
    DecimalFraction = 4
    BigFloat = 5
    Unclassified = 6


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

    def write_string(self, val: str):
        """Write string as cbor formatted

        Args:
            val (str): value to be encoded and written to the encoded data.
        """
        return _awscrt.cbor_encoder_write_str(self._binding, val)

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
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborElementType.Null)

    def write_bool(self, val: bool):
        return _awscrt.cbor_encoder_write_bool(self._binding, val)

    def write_data_item(self, data_item: Any):
        """Generic API to write any type of an data_item as cbor formatted.
        TODO: timestamp <-> datetime?? Decimal fraction <-> decimal??

        Args:
            data_item (Any): any type of data_item. If the type is not supported to be converted to cbor format, ValueError will be raised.
        """
        if isinstance(data_item, str):
            self.write_string(data_item)
        elif isinstance(data_item, bytes):
            self.write_bytes(data_item)
        elif isinstance(data_item, int):
            self.write_int(data_item)
        elif isinstance(data_item, float):
            self.write_float(data_item)
        elif isinstance(data_item, dict):
            self.write_dict(data_item)
        elif isinstance(data_item, list):
            self.write_list(data_item)
        elif isinstance(data_item, bool):
            self.write_bool(data_item)
        elif data_item is None:
            self.write_null()
        else:
            raise ValueError(f"not supported type for data_item: {data_item}")

    def write_list(self, val: list):
        return _awscrt.cbor_encoder_write_py_list(self._binding, val)

    def write_dict(self, val: dict):
        return _awscrt.cbor_encoder_write_py_dict(self._binding, val)

    def write_data_item_2(self, data_item: Any):
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

    def peek_next_type(self) -> AwsCborElementType:
        return AwsCborElementType(_awscrt.cbor_decoder_peek_type(self._binding))

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
        return _awscrt.cbor_decoder_pop_next_double(self._binding)

    def pop_next_bool(self) -> bool:
        return _awscrt.cbor_decoder_pop_next_bool(self._binding)

    def pop_next_bytes(self) -> bytes:
        return _awscrt.cbor_decoder_pop_next_bytes(self._binding)

    def pop_next_str(self) -> str:
        return _awscrt.cbor_decoder_pop_next_str(self._binding)

    def pop_next_array_start(self) -> int:
        return _awscrt.cbor_decoder_pop_next_array_start(self._binding)

    def pop_next_map_start(self) -> int:
        return _awscrt.cbor_decoder_pop_next_map_start(self._binding)

    def pop_next_tag_val(self) -> int:
        return _awscrt.cbor_decoder_pop_next_tag_val(self._binding)

    def pop_next_numeric(self) -> Union[int, float]:
        type = _awscrt.cbor_decoder_peek_type(self._binding)
        if type == AwsCborElementType.UnsignedInt:
            return self.pop_next_unsigned_int()
        elif type == AwsCborElementType.NegativeInt:
            return self.pop_next_negative_int()
        elif type == AwsCborElementType.Float:
            return self.pop_next_double()
        # TODO: support bignum?
        # TODO: Instead of ValueError, probably raise the same error from C with the same AWS_ERROR_CBOR_UNEXPECTED_TYPE
        raise ValueError("the cbor src is not a numeric type to decode")

    def pop_next_inf_bytes(self) -> bytes:
        type = _awscrt.cbor_decoder_peek_type(self._binding)
        if type != AwsCborElementType.InfBytes:
            raise ValueError("the cbor src is not an indefinite bytes to decode")
        result = b""
        # Consume the inf_bytes
        self.consume_next_element()
        while type != AwsCborElementType.Break:
            result += self.pop_next_bytes()
            type = _awscrt.cbor_decoder_peek_type(self._binding)
        # Consume the break
        self.consume_next_element()
        return result

    def pop_next_inf_str(self) -> bytes:
        type = _awscrt.cbor_decoder_peek_type(self._binding)
        if type != AwsCborElementType.InfStr:
            raise ValueError("the cbor src is not an indefinite string to decode")
        result = ""
        # Consume the inf_str
        self.consume_next_element()
        while type != AwsCborElementType.Break:
            result += self.pop_next_str()
            type = _awscrt.cbor_decoder_peek_type(self._binding)
        # Consume the break
        self.consume_next_element()
        return result

    def pop_next_list(self) -> list:
        # return _awscrt.cbor_decoder_pop_next_py_list(self._binding)
        type = _awscrt.cbor_decoder_peek_type(self._binding)
        return_val = []
        if type == AwsCborElementType.InfArray:
            # Consume the inf_array
            self.consume_next_element()
            while type != AwsCborElementType.Break:
                return_val.append(self.pop_next_data_item())
                type = _awscrt.cbor_decoder_peek_type(self._binding)
            # Consume the break
            self.consume_next_element()
            return return_val
        elif type == AwsCborElementType.ArrayStart:
            number_elements = self.pop_next_array_start()
            for i in range(number_elements):
                return_val.append(self.pop_next_data_item())
            return return_val
        else:
            raise ValueError("the cbor src is not a list to decode")

    def pop_next_map(self) -> dict:
        # return _awscrt.cbor_decoder_pop_next_py_dict(self._binding)
        type = _awscrt.cbor_decoder_peek_type(self._binding)
        return_val = {}
        if type == AwsCborElementType.InfMap:
            # Consume the inf_map
            self.consume_next_element()
            while type != AwsCborElementType.Break:
                return_val[self.pop_next_data_item()] = self.pop_next_data_item()
                type = _awscrt.cbor_decoder_peek_type(self._binding)
            # Consume the break
            self.consume_next_element()
            return return_val
        elif type == AwsCborElementType.MapStart:
            number_elements = self.pop_next_map_start()
            for i in range(number_elements):
                key = self.pop_next_data_item()
                value = self.pop_next_data_item()
                return_val[key] = value
            return return_val
        else:
            raise ValueError("the cbor src is not a map to decode")

    def pop_next_data_item(self) -> Any:
        # TODO: timestamp, decimal fraction
        # TODO: maybe wrote all those if elif in the binding level, so that we can use switch at least???
        #   And possible to avoid some call cross language boundary???
        # TODO: If it fails in the middle, with bunch of stuff already popped. Do we want a way to resume??
        type = _awscrt.cbor_decoder_peek_type(self._binding)
        if type == AwsCborElementType.UnsignedInt or \
                type == AwsCborElementType.NegativeInt or \
                type == AwsCborElementType.Float:
            return self.pop_next_numeric()
        elif type == AwsCborElementType.Bytes:
            return self.pop_next_bytes()
        elif type == AwsCborElementType.String:
            return self.pop_next_str()
        elif type == AwsCborElementType.Bool:
            return self.pop_next_bool()
        elif type == AwsCborElementType.Null or \
                type == AwsCborElementType.Undefined:
            # Treat both NULL and Undefined as None.
            self.consume_next_element()
            return None
        elif type == AwsCborElementType.ArrayStart or \
                type == AwsCborElementType.InfArray:
            return self.pop_next_list()
        elif type == AwsCborElementType.MapStart or \
                type == AwsCborElementType.InfMap:
            return self.pop_next_map()
        elif type == AwsCborElementType.InfBytes:
            return self.pop_next_inf_bytes()
        elif type == AwsCborElementType.InfStr:
            return self.pop_next_inf_str()
        elif type == AwsCborElementType.Tag:
            tag_val = self.pop_next_tag_val()
            if tag_val == AwsCborTags.NegativeBigNum:
                bytes_val = self.pop_next_bytes()
                return -1 - int.from_bytes(bytes_val, "big")
            elif tag_val == AwsCborTags.UnsignedBigNum:
                bytes_val = self.pop_next_bytes()
                return int.from_bytes(bytes_val, "big")
            else:
                raise ValueError(f"unsupported tag value: {tag_val}")
        else:
            raise ValueError(f"unsupported type: {type.name}")

    def pop_next_data_item_2(self) -> Any:
        return _awscrt.cbor_decoder_pop_next_data_item(self._binding)
