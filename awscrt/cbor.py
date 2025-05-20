# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt

from awscrt import NativeResource
from enum import IntEnum
from typing import Callable, Any, Union


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
    """ Encoder for CBOR
        This class is used to encode data into CBOR format.
        Typical usage of encoder:
        - create an instance of AwsCborEncoder
        - call write_* methods to write data into the encoder
        - call get_encoded_data() to get the encoded data
        - call reset() to clear the encoder for next use
    """

    def __init__(self):
        super().__init__()
        self._binding = _awscrt.cbor_encoder_new()

    def get_encoded_data(self) -> bytes:
        """Return the current encoded data as bytes

        Returns:
            bytes: The encoded data currently
        """
        return _awscrt.cbor_encoder_get_encoded_data(self._binding)

    def reset(self):
        """Clear the current encoded data to empty bytes
        """
        return _awscrt.cbor_encoder_reset(self._binding)

    def write_int(self, val: int):
        """Write an int as cbor formatted,
            val less than -2^64 will be encoded as Negative bignum for CBOR
            val between -2^64 to -1, inclusive, will be encode as negative integer for CBOR
            val between 0 to 2^64 - 1, inclusive, will be encoded as unsigned integer for CBOR
            val greater than 2^64 - 1 will be encoded as Unsigned bignum for CBOR (Not implemented yet)

        Args:
            val (int): value to be encoded and written to the encoded data.
        """
        val_to_encode = val
        if val < 0:
            # For negative value, the value to encode is -1 - val.
            val_to_encode = -1 - val
        if val >= 0:
            return _awscrt.cbor_encoder_write_uint(self._binding, val_to_encode)
        else:
            return _awscrt.cbor_encoder_write_negint(self._binding, val_to_encode)

    def write_float(self, val: float):
        """Write a double as cbor formatted
            If the val can be convert the int without loss of precision,
            it will be converted to int to be written to as cbor formatted.

        Args:
            val (float): value to be encoded and written to the encoded data.
        """
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
            A logistic with the `number_entries`
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
        """Add a tag number.
        Notes: it's user's responsibility to keep the integrity of the tagged value to follow the RFC8949 section 3.4

        Args:
            tag_number (int): the tag number, refer to RFC8949 section 3.4 for the valid tag number.
        """
        if tag_number < 0 or tag_number > 2**64:
            raise ValueError()

        return _awscrt.cbor_encoder_write_tag(self._binding, tag_number)

    def write_null(self):
        """Add a simple value 22 as null. Refer to RFC8949 section 3.3
        """
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.Null)

    def write_undefined(self):
        """Add a simple value 23 as undefined. Refer to RFC8949 section 3.3
        """
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.Undefined)

    def write_indef_array_start(self):
        """Begin an indefinite-length array. Must be closed with write_break().
        Refer to RFC8949 section 3.2.2
        """
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.IndefArray)

    def write_indef_map_start(self):
        """Begin an indefinite-length map. Must be closed with write_break().
        Refer to RFC8949 section 3.2.2
        """
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.IndefMap)

    def write_indef_bytes_start(self):
        """Begin an indefinite-length byte string. Must be followed by definite-length
        byte strings and closed with write_break().
        Refer to RFC8949 section 3.2.2
        """
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.IndefBytes)

    def write_indef_text_start(self):
        """Begin an indefinite-length text string. Must be followed by definite-length
        text strings and closed with write_break().
        Refer to RFC8949 section 3.2.2
        """
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.IndefStr)

    def write_break(self):
        """Write a break code (0xFF) to close an indefinite-length item.
        Refer to RFC8949 section 3.2.2
        """
        return _awscrt.cbor_encoder_write_simple_types(self._binding, AwsCborType.Break)

    def write_bool(self, val: bool):
        """Add a simple value 20/21 as false/true. Refer to RFC8949 section 3.3
        """
        return _awscrt.cbor_encoder_write_bool(self._binding, val)

    def write_epoch_time(self, val: float):
        """Helper to write second-based epoch time as cbor formatted
        Args:
            val (float): second-based epoch time, float value to represent the precision less than 1 second.
        """
        # The epoch time is a tag 1, which is defined in RFC8949 section 3.4
        _awscrt.cbor_encoder_write_tag(self._binding, 1)
        # write the epoch time as float, which will be encoded as small as possible without loss of precision.
        return _awscrt.cbor_encoder_write_float(self._binding, val)

    def write_list(self, val: list):
        """Generic helper API to write the whole list as cbor formatted.
        The content of the list will be encoded as data_item.
        """
        return _awscrt.cbor_encoder_write_py_list(self._binding, val)

    def write_dict(self, val: dict):
        """Generic helper API to write the whole dict as cbor formatted.
        The content of the dict will be encoded as data_item.
        """
        return _awscrt.cbor_encoder_write_py_dict(self._binding, val)

    def write_data_item(self, data_item: Any):
        """Generic API to write any type of an data_item as cbor formatted.
        Specifically, it will be based on the type of data_item to decide how to encode it.
        The supported type of data_item are:
        - int
        - float
        - bool
        - bytes
        - str
        - list
        - dict

        Args:
            data_item (Any): any type of data_item. If the type is not supported to be converted to cbor format, ValueError will be raised.
        """
        return _awscrt.cbor_encoder_write_data_item(self._binding, data_item)


class AwsCborDecoder(NativeResource):
    """ Decoder for CBOR
        This class is used to decode a bytes of CBOR encoded data to python objects.
        Typical usage of decoder:
        - create an instance of AwsCborDecoder with bytes of cbor formatted data to be decoded
        - call peek_next_type() to get the type of the next data item
        - call pop_next_*() to based on the type of the next data item to decode it
        - Until expected data decoded, call get_remaining_bytes_len() to check if there is any remaining bytes left.
        - call reset_src() to reset the src data to be decoded, if needed.
    """

    def __init__(self, src: bytes, on_epoch_time: Callable[[Union[int, float]], Any] = None, **kwargs):
        """Create an instance of AwsCborDecoder with the src data to be decoded.
        The src data should be a bytes of cbor formatted data.

        Args:
            src (bytes): the bytes of cbor formatted data to be decoded.
            on_epoch_time (Callable[[int, Any], Any], optional): Optional callback invoked once tags
                with id: 1, which is the epoch time, are encountered during decoding a data_item.

                The function should take the following arguments:
                    *   `epoch_secs` (int | float): the seconds since epoch.

                The function should return
                    *   `result` (Any): The PyObject the epoch time converted to.
        """
        super().__init__()
        self._src = src
        self._binding = _awscrt.cbor_decoder_new(self, src)
        self._on_epoch_time = on_epoch_time

    def _on_epoch_time_callback(self, epoch_secs: Union[int, float]) -> Any:
        if self._on_epoch_time is not None:
            return self._on_epoch_time(epoch_secs)
        else:
            # just default to the numeric type.
            return epoch_secs

    def peek_next_type(self) -> AwsCborType:
        """Return the AwsCborType of the next data item in the cbor formatted data
        """
        return AwsCborType(_awscrt.cbor_decoder_peek_type(self._binding))

    def get_remaining_bytes_len(self) -> int:
        """Return the number of bytes not consumed yet of the src data.
        """
        return _awscrt.cbor_decoder_get_remaining_bytes_len(self._binding)

    def get_remaining_bytes(self) -> bytes:
        """Return the remaining bytes not consumed yet of the src data.
        """
        remaining_length = _awscrt.cbor_decoder_get_remaining_bytes_len(self._binding)
        return self._src[-remaining_length:] if remaining_length > 0 else b''

    def reset_src(self, src: bytes):
        """Reset the src data to be decoded.
        Note: the previous src data will be discarded.
            Use `get_remaining_bytes` to fetch the remaining bytes if needed before invoking this function.
        """
        self._src = src
        _awscrt.cbor_decoder_reset_src(self._binding, src)

    def consume_next_single_element(self):
        """
        Consume the next single element, without the content followed by the element.

        As an example for the following cbor, this function will only consume the
        0xBF, "Start indefinite-length map", not any content of the map represented.
        The next element to decode will start from 0x63:

        0xbf6346756ef563416d7421ff
        BF         -- Start indefinite-length map
        63         -- First key, UTF-8 string length 3
            46756e --   "Fun"
        F5         -- First value, true
        63         -- Second key, UTF-8 string length 3
            416d74 --   "Amt"
        21         -- Second value, -2
        FF         -- "break"
        """
        return _awscrt.cbor_decoder_consume_next_element(self._binding)

    def consume_next_whole_data_item(self):
        """
        Consume the next data item, includes all the content within the data item.
        Specifically, it read extra for the types listed below:
        1. `AwsCborType.IndefArray`, `AwsCborType.IndefMap`, `AwsCborType.IndefBytes` and `AwsCborType.IndefStr`. It read until
            the `AwsCborType.Break` is read.
        2. `AwsCborType.ArrayStart` and `AwsCborType.MapStart`. It read the number of data items in the array/map.
        3. `AwsCborType.Tag`. It read the one extra data item as the value of the tag.

        As an example for the following cbor, this function will consume all the data
        as it's only one cbor data item, an indefinite map with 2 <key, value> pair:

        0xbf6346756ef563416d7421ff
        BF         -- Start indefinite-length map
        63         -- First key, UTF-8 string length 3
            46756e --   "Fun"
        F5         -- First value, true
        63         -- Second key, UTF-8 string length 3
            416d74 --   "Amt"
        21         -- Second value, -2
        FF         -- "break"
        """
        return _awscrt.cbor_decoder_consume_next_data_item(self._binding)

    def pop_next_unsigned_int(self) -> int:
        """Return and consume the next data item as unsigned int if it's a `AwsCborType.UnsignedInt`
        Otherwise, it will raise ValueError.
        """
        return _awscrt.cbor_decoder_pop_next_unsigned_int(self._binding)

    def pop_next_negative_int(self) -> int:
        """Return and consume the next data item as negative int if it's a `AwsCborType.NegativeInt`
        Otherwise, it will raise ValueError.
        """
        val = _awscrt.cbor_decoder_pop_next_negative_int(self._binding)
        return -1 - val

    def pop_next_double(self) -> float:
        """Return and consume the next data item as float if it's a `AwsCborType.Float`
        Otherwise, it will raise ValueError.
        """
        return _awscrt.cbor_decoder_pop_next_float(self._binding)

    def pop_next_bool(self) -> bool:
        """Return and consume the next data item as bool if it's a `AwsCborType.Bool`
        Otherwise, it will raise ValueError.
        """
        return _awscrt.cbor_decoder_pop_next_boolean(self._binding)

    def pop_next_bytes(self) -> bytes:
        """Return and consume the next data item as bytes if it's a `AwsCborType.Bytes`
        Otherwise, it will raise ValueError.
        """
        return _awscrt.cbor_decoder_pop_next_bytes(self._binding)

    def pop_next_text(self) -> str:
        """Return and consume the next data item as text if it's a `AwsCborType.Text`
        Otherwise, it will raise ValueError.
        """
        return _awscrt.cbor_decoder_pop_next_text(self._binding)

    def pop_next_array_start(self) -> int:
        """Return and consume the next data item as int if it's a `AwsCborType.ArrayStart`
        Otherwise, it will raise ValueError.
        The return value is the number of date items followed as the content of the array.

        Notes: For indefinite-length, this function will fail with unexpected type. The designed way to
        handle indefinite-length array is:
        - Get `AwsCborType.IndefArray` from `peek_next_type`
        - call `consume_next_single_element` to pop the indefinite-length start.
        - Decode the next data item until `AwsCborType.Break` read.
        """
        return _awscrt.cbor_decoder_pop_next_array_start(self._binding)

    def pop_next_map_start(self) -> int:
        """Return and consume the next data item as int if it's a `AwsCborType.MapStart`
        Otherwise, it will raise ValueError.
        The return value is the number of paired date items followed as the content of the map.

        Notes: For indefinite-length, this function will fail with unexpected type.
        """
        return _awscrt.cbor_decoder_pop_next_map_start(self._binding)

    def pop_next_tag_val(self) -> int:
        """Return and consume the next data item as int if it's a `AwsCborType.Tag`
        Otherwise, it will raise ValueError.

        The return value is the tag ID. Refer the RFC8949 section 3.4 for
        corresponding expected data item to follow by the tag id as value.
        """
        return _awscrt.cbor_decoder_pop_next_tag(self._binding)

    def pop_next_list(self) -> list:
        """Return and consume the next data item as list if it's a `AwsCborType.ArrayStart` or `AwsCborType.IndefArray`
        Otherwise, it will raise ValueError.
        It consumes the all the content of the array as `pop_next_data_item`.
        """
        return _awscrt.cbor_decoder_pop_next_py_list(self._binding)

    def pop_next_map(self) -> dict:
        """Return and consume the next data item as list if it's a `AwsCborType.MapStart` or `AwsCborType.IndefMap`
        Otherwise, it will raise ValueError.
        It consumes the all the content of the map as `pop_next_data_item`.
        """
        return _awscrt.cbor_decoder_pop_next_py_dict(self._binding)

    def pop_next_data_item(self) -> Any:
        """Generic API to decode cbor formatted data to a python object.
        This consumes the next data item and return the decoded object.
        The type of the python object will be based on the cbor data item type.
        a full map from the cbor data item type to the python object type is:
        - `AwsCborType.UnsignedInt` or `AwsCborType.NegativeInt` -> int
        - `AwsCborType.Float` -> float
        - `AwsCborType.Bytes` or `AwsCborType.IndefBytes` -> bytes
        - `AwsCborType.Text` or `AwsCborType.IndefStr` -> str
        - `AwsCborType.Null` or `AwsCborType.Undefined` -> none
        - `AwsCborType.Bool` -> bool
        - `AwsCborType.ArrayStart` or `AwsCborType.IndefArray` and all the followed data items in the array -> list
        - `AwsCborType.MapStart` or `AwsCborType.IndefMap` and all the followed data items in the map -> dict
        - `AwsCborType.Tag`: For tag with id 1, as the epoch time, it invokes the _on_epoch_time for python to convert to expected type.
                             For the reset tag, exception will be raised.
        """
        return _awscrt.cbor_decoder_pop_next_data_item(self._binding)

    # def _pop_next_data_item_sdk(self) -> Any:
    #     """Helper function to decode cbor formatted data to a python object.
    #     It based on `pop_next_data_item` with the following specific rules for SDKs:
    #     1. It the content in a collection has None, it will be ignored
    #         - If a value in the list is None, the list will NOT include the None value.
    #         - If a value or key in the dict is None, the dict will NOT include the key/value pair.
    #     2. For epoch time, it will be converted to datetime object.
    #     3. All other tag will not be supported and raise error.
    #     """
    #     return _awscrt.cbor_decoder_pop_next_data_item_sdk(self._binding)
