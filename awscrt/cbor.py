# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt

from awscrt import NativeResource
from enum import IntEnum
from typing import Callable, Any, Union, Dict


class AwsCborType(IntEnum):
    """CBOR data type enumeration.

    Corresponds to `enum aws_cbor_type` in aws/common/cbor.h from AWS C Common Runtime.
    These values represent the different types of data items that can be encoded/decoded in CBOR format
    according to RFC 8949.

    Attributes:
        Unknown: Unknown/uninitialized type
        UnsignedInt: Unsigned integer (major type 0)
        NegativeInt: Negative integer (major type 1)
        Float: Floating-point number (major type 7, simple value 25/26/27)
        Bytes: Byte string (major type 2)
        Text: Text string (major type 3)
        ArrayStart: Start of definite-length array (major type 4)
        MapStart: Start of definite-length map (major type 5)
        Tag: Semantic tag (major type 6)
        Bool: Boolean value (major type 7, simple value 20/21)
        Null: Null value (major type 7, simple value 22)
        Undefined: Undefined value (major type 7, simple value 23)
        Break: Break stop code for indefinite-length items (major type 7, simple value 31)
        IndefBytes: Start of indefinite-length byte string (major type 2)
        IndefStr: Start of indefinite-length text string (major type 3)
        IndefArray: Start of indefinite-length array (major type 4)
        IndefMap: Start of indefinite-length map (major type 5)
    """
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


class ShapeBase:
    """
    Base class for shape objects used by CRT CBOR encoding.

    This class defines the interface that shape implementations should follow.
    Libraries can extend this class directly to provide shape information
    to the CBOR encoder without requiring intermediate conversions.

    Subclasses must implement the type_name property and can override other
    properties as needed based on their shape type.
    """

    @property
    def type_name(self) -> str:
        """
        Return the shape type name.
        TODO: maybe return the `AwsCborType` instead?

        Returns:
            str: One of: 'structure', 'list', 'map', 'string', 'integer', 'long',
                 'float', 'double', 'boolean', 'blob', 'timestamp'

        Note:
            Subclasses must implement this property.
        """
        raise NotImplementedError("Subclasses must implement type_name property")

    @property
    def members(self) -> Dict[str, 'ShapeBase']:
        """
        For structure types, return dict of member name -> ShapeBase.

        Returns:
            Dict[str, ShapeBase]: Dictionary mapping member names to their shapes

        Raises:
            AttributeError: If called on non-structure type
        """
        raise AttributeError(f"Shape type {self.type_name} has no members")

    @property
    def member(self) -> 'ShapeBase':
        """
        For list types, return the ShapeBase of list elements.

        Returns:
            ShapeBase: Shape of list elements

        Raises:
            AttributeError: If called on non-list type
        """
        raise AttributeError(f"Shape type {self.type_name} has no member")

    @property
    def key(self) -> 'ShapeBase':
        """
        For map types, return the ShapeBase of map keys.

        Returns:
            ShapeBase: Shape of map keys

        Raises:
            AttributeError: If called on non-map type
        """
        raise AttributeError(f"Shape type {self.type_name} has no key")

    @property
    def value(self) -> 'ShapeBase':
        """
        For map types, return the ShapeBase of map values.

        Returns:
            ShapeBase: Shape of map values

        Raises:
            AttributeError: If called on non-map type
        """
        raise AttributeError(f"Shape type {self.type_name} has no value")

    def get_serialization_name(self, member_name: str) -> str:
        """
        Get the serialization name for a structure member.

        For structure types, returns the name to use in CBOR encoding.
        This allows for custom field name mappings (e.g., 'user_id' -> 'UserId').

        Args:
            member_name: The member name as it appears in the structure

        Returns:
            str: The name to use in CBOR encoding (may be same as member_name)

        Raises:
            AttributeError: If called on non-structure type
            ValueError: If member_name is not found in the structure
        """
        raise AttributeError(f"Shape type {self.type_name} has no serialization_name")


class AwsCborEncoder(NativeResource):
    """CBOR encoder for converting Python objects to CBOR binary format.

    This class provides methods to encode various Python data types into CBOR (Concise Binary Object
    Representation) format as defined in RFC 8949. The encoder builds CBOR data incrementally by
    calling write_* methods in sequence.

    Thread Safety:
        This class is NOT thread-safe. Each encoder instance should only be used from a single thread.
        Create separate encoder instances for concurrent encoding operations.

    Memory Management:
        The encoder automatically manages internal memory and integrates with AWS CRT memory management.
        Call reset() to clear internal buffers for reuse, or let the encoder be garbage collected.

    Typical Usage:
        ```python
        encoder = AwsCborEncoder()
        encoder.write_int(42)
        encoder.write_text("hello")
        encoder.write_array_start(2)
        encoder.write_bool(True)
        encoder.write_null()
        cbor_data = encoder.get_encoded_data()
        ```

    For complex data structures, use write_data_item() which automatically handles nested objects:
        ```python
        encoder = AwsCborEncoder()
        data = {"numbers": [1, 2, 3], "text": "example", "flag": True}
        encoder.write_data_item(data)
        cbor_data = encoder.get_encoded_data()
        ```
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
        """Clear the encoder's internal buffer and reset to initial state.

        After calling this method, the encoder is ready to encode new data from scratch.
        Any previously encoded data is discarded and cannot be recovered.

        This is useful for reusing the same encoder instance to encode multiple
        independent CBOR documents without creating new encoder objects.

        Note:
            This operation does not raise exceptions and always succeeds.
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
        if val >= 0:
            return _awscrt.cbor_encoder_write_uint(self._binding, val)
        else:
            # For negative value, the value to encode is -1 - val.
            val_to_encode = -1 - val
            return _awscrt.cbor_encoder_write_negint(self._binding, val_to_encode)

    def write_float(self, val: float):
        """Write a double as cbor formatted
            Encodes as the most compact CBOR representation without loss of precision.

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
            for a number of the cbor data items to be included in the array.
            `number_entries` should 0 to 2^64 inclusive.
            Otherwise, ValueError will be raised.

        Args:
            number_entries (int): number of entries in the array to be written
        """
        if number_entries < 0 or number_entries > 2**64:
            raise ValueError(f"{number_entries} must be between 0 and 2^64")

        return _awscrt.cbor_encoder_write_array_start(self._binding, number_entries)

    def write_map_start(self, number_entries: int):
        """Add a start of map element, with the `number_entries`
            for the number of pair of cbor data items to be included in the map.
            `number_entries` should 0 to 2^64 inclusive.
            Otherwise, ValueError will be raised.

        Args:
            number_entries (int): number of entries in the map to be written
        """
        if number_entries < 0 or number_entries > 2**64:
            raise ValueError(f"{number_entries} must be between 0 and 2^64")

        return _awscrt.cbor_encoder_write_map_start(self._binding, number_entries)

    def write_tag(self, tag_number: int):
        """Add a tag number.
        Notes: it's user's responsibility to keep the integrity of the tagged value to follow the RFC8949 section 3.4

        Args:
            tag_number (int): the tag number, refer to RFC8949 section 3.4 for the valid tag number.
        """
        if tag_number < 0 or tag_number > 2**64:
            raise ValueError(f"{tag_number} must be between 0 and 2^64")

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

    def write_data_item_shaped(self,
                               data_item: Any,
                               shape: 'ShapeBase',
                               timestamp_converter: Callable[[Any],
                                                             float] = None):
        """Generic API to write any type of data_item as cbor formatted, using shape information.

        The shape parameter must be a CRTShape wrapper object - a lightweight wrapper around
        botocore Shape objects that exposes only the properties needed by the CRT CBOR encoder.

        Supported shape types:
        - integer/long: Integer values
        - float/double: Floating point values
        - boolean: Boolean values
        - blob: Byte strings
        - string: Text strings
        - list: Lists with typed members
        - map: Maps with typed keys and values
        - structure: Structures with named members (None values filtered)
        - timestamp: Timestamps (with optional converter callback)

        Args:
            data_item (Any): The data to encode
            shape (CRTShape): A CRTShape wrapper object that wraps a botocore Shape
            timestamp_converter (Callable[[Any], float], optional): Optional callback to convert
                timestamp values to epoch seconds (float). If not provided, assumes data_item
                is already a numeric timestamp for timestamp shapes.

        Example:
            ```python
            from awscrt.cbor_shape import CRTShape

            encoder = AwsCborEncoder()

            # Wrap the botocore shape
            crt_shape = CRTShape(botocore_shape)

            # Encode data with shape information
            data = {"id": 123, "name": "Alice"}

            def timestamp_converter(dt):
                return dt.timestamp()

            encoder.write_data_item_shaped(data, crt_shape, timestamp_converter)
            cbor_bytes = encoder.get_encoded_data()
            ```

        For complete specification, see CRT_SHAPE_WRAPPER_APPROACH.md

        Note:
            The CRTShape wrapper provides lazy initialization and caching for optimal performance.
            Shape objects are typically cached by the serializer for reuse across multiple requests.
        """
        return _awscrt.cbor_encoder_write_data_item_shaped(self._binding, data_item, shape, timestamp_converter)


class AwsCborDecoder(NativeResource):
    """CBOR decoder for converting CBOR binary format to Python objects.

    This class provides methods to decode CBOR (Concise Binary Object Representation) binary data
    into Python data types as defined in RFC 8949. The decoder processes CBOR data sequentially
    using a peek-and-pop approach, allowing fine-grained control over the decoding process.

    Thread Safety:
        This class is NOT thread-safe. Each decoder instance should only be used from a single thread.
        Create separate decoder instances for concurrent decoding operations.

    Memory Management:
        The decoder holds a reference to the source data and automatically manages internal state.
        Use reset_src() to decode new data with the same decoder instance, or let the decoder
        be garbage collected when no longer needed.

    Decoding Workflow:
        The decoder uses a sequential peek-and-pop pattern:
        1. Use peek_next_type() to inspect the next data item type without consuming it
        2. Use appropriate pop_next_*() method to decode and consume the data item
        3. Repeat until all expected data is decoded
        4. Check get_remaining_bytes_len() to get the remaining unprocessed data.

    Basic Usage:
        ```python
        # Decode simple values
        decoder = AwsCborDecoder(cbor_data)
        if decoder.peek_next_type() == AwsCborType.UnsignedInt:
            value = decoder.pop_next_unsigned_int()
        ```

    Generic Decoding:
        For automatic type detection and conversion, use pop_next_data_item():
        ```python
        decoder = AwsCborDecoder(cbor_data)
        python_object = decoder.pop_next_data_item()  # Automatically handles any CBOR type
        ```

    Complex Structures:
        ```python
        decoder = AwsCborDecoder(cbor_data)

        # Manually decode an array
        if decoder.peek_next_type() == AwsCborType.ArrayStart:
            array_length = decoder.pop_next_array_start()
            items = []
            for _ in range(array_length):
                items.append(decoder.pop_next_data_item())

        # Or use the convenience method
        array = decoder.pop_next_list()  # Handles both definite and indefinite arrays
        ```

    Tagged Values and Callbacks:
        Handle semantic tags (like timestamps) with custom processing:
        ```python
        def handle_timestamp(epoch_secs):
            return datetime.fromtimestamp(epoch_secs, tz=timezone.utc)

        decoder = AwsCborDecoder(cbor_data, on_epoch_time=handle_timestamp)
        timestamp = decoder.pop_next_data_item()  # Returns datetime object for tag 1
        ```

    Error Handling:
        The decoder raises exceptions for malformed data, type mismatches, and unexpected end-of-data.
        Always handle these exceptions in production code:
        ```python
        try:
            decoder = AwsCborDecoder(cbor_data)
            result = decoder.pop_next_data_item()
        except ValueError as e:
            print(f"CBOR decoding error: {e}")
        ```
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
        """Return the remaining unprocessed CBOR data as bytes.

        This method returns a slice of the original source data that has not yet been
        consumed by the decoder. Useful for debugging, validation, or passing remaining
        data to another decoder instance.

        Returns:
            bytes: The remaining unprocessed CBOR data. Returns empty bytes (b'') if
                all data has been consumed.

        Warning:
            The returned bytes share memory with the original source data. Modifications
            to the source data after decoder creation may affect the returned bytes.
        """
        remaining_length = _awscrt.cbor_decoder_get_remaining_bytes_len(self._binding)
        if remaining_length <= 0:
            return b''
        start_idx = len(self._src) - remaining_length
        return self._src[start_idx:]

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

        Note: CBOR stores negative integers as -(val + 1), so we convert back
        to the actual negative value by computing -(val + 1) = -1 - val.
        """
        encoded_val = _awscrt.cbor_decoder_pop_next_negative_int(self._binding)
        return -1 - encoded_val

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
                             For the other tags, exception will be raised.
        """
        return _awscrt.cbor_decoder_pop_next_data_item(self._binding)
