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


class AwsCborEncoder(NativeResource):
    """ Encoder for CBOR """

    def __init__(self):
        super().__init__()
        self._binding = _awscrt.cbor_encoder_new()

    def get_encoded_data(self) -> bytes:
        return _awscrt.cbor_encoder_get_encoded_data(self._binding)

    def write_int(self, val: int):
        """Write an int as cbor formatted, -2^64 to 2^64 - 1 inclusive.
            Otherwise, overflow will be raised.

        Args:
            val (int): value to be encoded and written to the encoded data.
        """
        if val < -2**64 or val > 2**64 - 1:
            raise OverflowError(f"{val} is overflowed to be encoded into cbor integers")

        if val >= 0:
            return _awscrt.cbor_encoder_write_unsigned_int(self._binding, val)
        else:
            return _awscrt.cbor_encoder_write_negative_int(self._binding, -1 - val)

    def write_float(self, val: Union[int, float]):
        """Write a double as cbor formatted
            If the val can be convert the int without loss of precision,
            it will be converted to int to be written to as cbor formatted.

        Args:
            val (float): value to be encoded and written to the encoded data.
        """
        if isinstance(val, int):
            self.write_int(val)
        elif isinstance(val, float):
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
        TODO: timestamp?

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

    def write_dict(self, val: dict):
        self.write_map_start(len(val))
        for key, value in val.items():
            self.write_data_item(key)
            self.write_data_item(value)

    def write_list(self, val: list):
        self.write_array_start(len(val))
        for data_item in val:
            self.write_data_item(data_item)


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
        type = self.peek_next_type()
        if type == AwsCborElementType.UnsignedInt:
            return self.pop_next_unsigned_int()
        elif type == AwsCborElementType.NegativeInt:
            return self.pop_next_negative_int()
        elif type == AwsCborElementType.Float:
            return self.pop_next_double()
        # TODO: support bignum?
        raise ValueError("the cbor src is not a numeric type to decode")

    def pop_next_inf_bytes(self) -> bytes:
        type = self.peek_next_type()
        if type != AwsCborElementType.InfBytes:
            raise ValueError("the cbor src is not an indefinite bytes to decode")
        result = b""
        # Consume the inf_bytes
        self.consume_next_element()
        while type != AwsCborElementType.Break:
            result += self.pop_next_bytes()
            type = self.peek_next_type()
        # Consume the break
        self.consume_next_element()
        return result

    def pop_next_inf_str(self) -> bytes:
        type = self.peek_next_type()
        if type != AwsCborElementType.InfStr:
            raise ValueError("the cbor src is not an indefinite string to decode")
        result = ""
        # Consume the inf_str
        self.consume_next_element()
        while type != AwsCborElementType.Break:
            result += self.pop_next_str()
            type = self.peek_next_type()
        # Consume the break
        self.consume_next_element()
        return result

    def pop_next_list(self) -> list:
        type = self.peek_next_type()
        return_val = []
        if type == AwsCborElementType.InfArray:
            # Consume the inf_array
            self.consume_next_element()
            while type != AwsCborElementType.Break:
                return_val.append(self.pop_next_data_item())
                type = self.peek_next_type()
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
        type = self.peek_next_type()
        return_val = {}
        if type == AwsCborElementType.InfMap:
            # Consume the inf_map
            self.consume_next_element()
            while type != AwsCborElementType.Break:
                return_val[self.pop_next_data_item()] = self.pop_next_data_item()
                type = self.peek_next_type()
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
        # TODO: tag, timestamp
        # TODO: maybe wrote all those if elif in the binding level, so that we can use switch at least???
        type = self.peek_next_type()
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
        elif type == AwsCborElementType.Null:
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
        else:
            raise ValueError(f"unsupported type: {type.name}")
