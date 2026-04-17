# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from test import NativeResourceTest
from awscrt.cbor import *
import json
import struct
import os
import datetime


class TestCBOR(NativeResourceTest):
    def test_cbor_encode_decode_int(self):
        encoder = AwsCborEncoder()
        try:
            # pass float instead of int
            encoder.write_int(1.1)
        except TypeError as e:
            self.assertIsNotNone(e)
        else:
            self.assertTrue(False)

        val_to_write = [-100, 100, 2**64 - 1, -2**64]
        for val in val_to_write:
            encoder.write_int(val)

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        try:
            # The first val is a negative val.
            val = decoder.pop_next_unsigned_int()
        except RuntimeError as e:
            self.assertIsNotNone(e)
        else:
            self.assertTrue(False)

        for val in val_to_write:
            t = decoder.pop_next_data_item()
            self.assertEqual(t, val)

        self.assertEqual(decoder.get_remaining_bytes_len(), 0)

    def test_cbor_encode_decode_data_item(self):
        encoder = AwsCborEncoder()
        numerics = [-100.12, 100.0, -100, 100, 2**64 - 1, -2**64, 18446744073709551616.0]
        another_map = {
            # "bignum": 2**65,  # TODO: big number are not supported from C impl yet.
            # "negative bignum": -2**75,
            2**6: [1, 2, 3],
            -2**6: [1, ["2", b"3"], {"most complicated": numerics}, 2**6, -2**7]
        }
        val_to_write = {
            "mytest": b"write_test",
            b"test_more": another_map,
            2: {
                2.3: ["a", "b", "c"]
            },
            "empty map": {},
            "empty array": [],
            "True": True,
            "False": False,
            "empty str": "",
            "empty bytes": b"",
        }
        encoder.write_data_item(val_to_write)

        decoder = AwsCborDecoder(encoder.get_encoded_data())

        # Temp val only for easier to debug.
        t = decoder.pop_next_data_item()
        self.assertEqual(val_to_write, t)

    def test_cbor_encode_decode_indef(self):
        encoder = AwsCborEncoder()
        numerics = [-100.12, 100.0, -100, 100, 2**64 - 1, -2**64, 18446744073709551616.0]
        another_map = {
            2**6: [1, 2, 3],
            -2**6: [1, ["2", b"3"], {"most complicated": numerics}, 2**6, -2**7]
        }
        encoder.write_indef_array_start()
        for i in numerics:
            encoder.write_data_item(i)
        encoder.write_break()

        encoder.write_indef_map_start()
        for key in another_map:
            encoder.write_data_item(key)
            encoder.write_data_item(another_map[key])
        encoder.write_break()

        text1 = "test"
        text2 = "text"
        encoder.write_indef_text_start()
        encoder.write_text(text1)
        encoder.write_text(text2)
        encoder.write_break()

        bytes1 = b"test"
        bytes2 = b"bytes"
        encoder.write_indef_bytes_start()
        encoder.write_bytes(bytes1)
        encoder.write_bytes(bytes2)
        encoder.write_break()

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        # Temp val only for easier to debug.
        t = decoder.pop_next_data_item()
        self.assertEqual(numerics, t)
        t = decoder.pop_next_data_item()
        self.assertEqual(another_map, t)
        t = decoder.pop_next_data_item()
        self.assertEqual(text1 + text2, t)
        t = decoder.pop_next_data_item()
        self.assertEqual(bytes1 + bytes2, t)
        self.assertEqual(0, decoder.get_remaining_bytes_len())

    def test_cbor_encode_decode_epoch_time(self):
        time_stamp_secs = 100.1  # some random time

        encoder = AwsCborEncoder()
        encoder.write_tag(1)  # tag time
        encoder.write_float(time_stamp_secs)

        def on_epoch_time(epoch_secs):
            return datetime.datetime.fromtimestamp(epoch_secs)

        # without the handler for epoch time, it just return the numeric.
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        t = decoder.pop_next_data_item()
        self.assertEqual(time_stamp_secs, t)

        # add handler
        decoder = AwsCborDecoder(encoder.get_encoded_data(), on_epoch_time)
        t = decoder.pop_next_data_item()
        self.assertEqual(datetime.datetime.fromtimestamp(time_stamp_secs), t)

    def test_cbor_encode_decode_unexpected_tag(self):
        time_stamp_secs = 100.1  # some random time

        encoder = AwsCborEncoder()
        encoder.write_tag(0)  # tag time
        encoder.write_float(time_stamp_secs)

        def on_epoch_time(epoch_secs):
            return datetime.datetime.fromtimestamp(epoch_secs)
        # add handler
        decoder = AwsCborDecoder(encoder.get_encoded_data(), on_epoch_time)
        exception = None
        try:
            t = decoder.pop_next_data_item()
        except Exception as e:
            exception = e
        self.assertIsNotNone(exception)

    def test_cbor_encode_unsupported_type(self):
        """Test that encoding unsupported types raises ValueError"""
        # Create a custom class that's not supported by CBOR encoder
        class CustomClass:
            def __init__(self, value):
                self.value = value

        # Try to encode an unsupported type
        encoder = AwsCborEncoder()
        unsupported_obj = CustomClass(42)

        # Should raise ValueError with message about unsupported type
        with self.assertRaises(ValueError) as context:
            encoder.write_data_item(unsupported_obj)
        # Verify the error message mentions "Not supported type"
        self.assertIn("Not supported type", str(context.exception))

        # Test unsupported type in a list (should also fail)
        encoder2 = AwsCborEncoder()
        with self.assertRaises(ValueError) as context2:
            encoder2.write_data_item([1, 2, unsupported_obj, 3])

        self.assertIn("Not supported type", str(context2.exception))

        # Test unsupported type as dict key (should also fail)
        encoder3 = AwsCborEncoder()
        with self.assertRaises(ValueError) as context3:
            encoder3.write_data_item({unsupported_obj: "value"})

        self.assertIn("Not supported type", str(context3.exception))

    def test_cbor_encode_decode_special_floats(self):
        """Test encoding and decoding special float values: inf, -inf, and NaN"""
        import math

        # Test positive infinity
        encoder = AwsCborEncoder()
        pos_inf = float('inf')
        encoder.write_float(pos_inf)
        print(encoder.get_encoded_data())
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        decoded_pos_inf = decoder.pop_next_data_item()
        print(decoded_pos_inf)
        self.assertTrue(math.isinf(decoded_pos_inf))
        self.assertTrue(decoded_pos_inf > 0)

        # Test negative infinity
        encoder = AwsCborEncoder()
        neg_inf = float('-inf')
        encoder.write_float(neg_inf)

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        decoded_neg_inf = decoder.pop_next_data_item()
        self.assertTrue(math.isinf(decoded_neg_inf))
        self.assertTrue(decoded_neg_inf < 0)

        # Test NaN
        encoder = AwsCborEncoder()
        nan_val = float('nan')
        encoder.write_float(nan_val)

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        decoded_nan = decoder.pop_next_data_item()
        self.assertTrue(math.isnan(decoded_nan))

        # Test special floats in a list using write_data_item
        encoder = AwsCborEncoder()
        special_floats_list = [float('inf'), float('-inf'), float('nan'), 42.0, -100.5]
        encoder.write_data_item(special_floats_list)

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        decoded_list = decoder.pop_next_data_item()
        self.assertEqual(len(decoded_list), 5)
        self.assertTrue(math.isinf(decoded_list[0]) and decoded_list[0] > 0)
        self.assertTrue(math.isinf(decoded_list[1]) and decoded_list[1] < 0)
        self.assertTrue(math.isnan(decoded_list[2]))
        self.assertEqual(decoded_list[3], 42.0)
        self.assertEqual(decoded_list[4], -100.5)

        # Test special floats in a dictionary
        encoder = AwsCborEncoder()
        special_floats_dict = {
            "positive_infinity": float('inf'),
            "negative_infinity": float('-inf'),
            "not_a_number": float('nan'),
            "normal": 3.14
        }
        encoder.write_data_item(special_floats_dict)

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        decoded_dict = decoder.pop_next_data_item()
        self.assertTrue(math.isinf(decoded_dict["positive_infinity"]) and decoded_dict["positive_infinity"] > 0)
        self.assertTrue(math.isinf(decoded_dict["negative_infinity"]) and decoded_dict["negative_infinity"] < 0)
        self.assertTrue(math.isnan(decoded_dict["not_a_number"]))
        self.assertEqual(decoded_dict["normal"], 3.14)

        # Test special floats in nested structures
        encoder = AwsCborEncoder()
        nested_structure = {
            "data": [
                {"value": float('inf'), "type": "infinity"},
                {"value": float('-inf'), "type": "negative_infinity"},
                {"value": float('nan'), "type": "nan"}
            ],
            "metadata": {
                "max": float('inf'),
                "min": float('-inf')
            }
        }
        encoder.write_data_item(nested_structure)

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        decoded_nested = decoder.pop_next_data_item()
        self.assertTrue(math.isinf(decoded_nested["data"][0]["value"]) and decoded_nested["data"][0]["value"] > 0)
        self.assertTrue(math.isinf(decoded_nested["data"][1]["value"]) and decoded_nested["data"][1]["value"] < 0)
        self.assertTrue(math.isnan(decoded_nested["data"][2]["value"]))
        self.assertTrue(math.isinf(decoded_nested["metadata"]["max"]) and decoded_nested["metadata"]["max"] > 0)
        self.assertTrue(math.isinf(decoded_nested["metadata"]["min"]) and decoded_nested["metadata"]["min"] < 0)

        self.assertEqual(decoder.get_remaining_bytes_len(), 0)

    def _ieee754_bits_to_float(self, bits):
        return struct.unpack('>f', struct.pack('>I', bits))[0]

    def _ieee754_bits_to_double(self, bits):
        return struct.unpack('>d', struct.pack('>Q', bits))[0]

    def _convert_expect(self, expect):
        if isinstance(expect, dict):
            if 'uint' in expect:
                return expect['uint']
            elif 'negint' in expect:
                return expect['negint']
            elif 'bool' in expect:
                return expect['bool']
            elif 'float32' in expect:
                return self._ieee754_bits_to_float(expect['float32'])
            elif 'float64' in expect:
                return self._ieee754_bits_to_double(expect['float64'])
            elif 'null' in expect:
                return None
            elif 'bytestring' in expect:
                return bytes(expect['bytestring'])
            elif 'string' in expect:
                return expect['string']
            elif 'list' in expect:
                return [self._convert_expect(item) for item in expect['list']]
            elif 'map' in expect:
                return {k: self._convert_expect(v) for k, v in expect['map'].items()}
        return expect

    def test_cbor_decode_success(self):
        """Test CBOR decoding using test cases from JSON file"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(current_dir, 'resources', 'decode-success-tests.json')
        with open(test_file, 'r') as f:
            test_cases = json.load(f)

        for case in test_cases:
            description = case.get("description", "No description")
            input_hex = case.get("input")
            expected = self._convert_expect(case.get("expect"))

            with self.subTest(description=description):
                # Convert hex input to bytes
                try:
                    bytes_input = bytes.fromhex(input_hex)
                except ValueError as e:
                    self.fail(f"Failed to convert hex input: {e}")

                # Decode the CBOR data
                try:
                    decoder = AwsCborDecoder(bytes_input)
                    type = decoder.peek_next_type()
                    if type == AwsCborType.Tag:
                        # TODO: we don't support parse the tag to python type yet.
                        # hard code the tag cases to the expected format.
                        tag_id = decoder.pop_next_tag_val()
                        if tag_id == 0:
                            tag_value_type = "string"
                        else:
                            tag_value_type = "uint"
                        tag_data = decoder.pop_next_data_item()
                        decoded_data = {
                            "tag": {
                                "id": tag_id,
                                "value": {
                                    tag_value_type: tag_data
                                }
                            }
                        }
                    else:
                        decoded_data = decoder.pop_next_data_item()

                    self.assertEqual(
                        decoded_data,
                        expected,
                        f"Failed case '{description}'\nDecoded: {decoded_data}\nExpected: {expected}"
                    )
                except Exception as e:
                    self.fail(f"Failed to decode CBOR data: {e}")

    def test_cbor_decode_errors(self):
        """Test CBOR decoding error cases from JSON file"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(current_dir, 'resources', 'decode-error-tests.json')

        with open(test_file, 'r') as f:
            test_cases = json.load(f)

        for case in test_cases:
            description = case.get("description", "No description")
            input_hex = case.get("input")

            with self.subTest(description=description):
                # Convert hex input to bytes
                try:
                    bytes_input = bytes.fromhex(input_hex)
                except ValueError as e:
                    self.fail(f"Failed to convert hex input: {e}")

                # Decode the CBOR data - should raise an exception
                decoder = AwsCborDecoder(bytes_input)

                with self.assertRaises(RuntimeError):
                    type = decoder.peek_next_type()
                    if type == AwsCborType.Tag:
                        tag_id = decoder.pop_next_tag_val()
                        tag_data = decoder.pop_next_data_item()
                    else:
                        decoded_data = decoder.pop_next_data_item()

    # Helper shape classes for testing write_data_item_shaped
    class SimpleShape(ShapeBase):
        """Simple shape implementation for testing"""

        def __init__(self, type_name):
            self._type_name = type_name

        @property
        def type_name(self):
            return self._type_name

    class ListShape(ShapeBase):
        """List shape implementation for testing"""

        def __init__(self, member_shape):
            self._member_shape = member_shape

        @property
        def type_name(self):
            return "list"

        @property
        def member(self):
            return self._member_shape

    class MapShape(ShapeBase):
        """Map shape implementation for testing"""

        def __init__(self, key_shape, value_shape):
            self._key_shape = key_shape
            self._value_shape = value_shape

        @property
        def type_name(self):
            return "map"

        @property
        def key(self):
            return self._key_shape

        @property
        def value(self):
            return self._value_shape

    class StructureShape(ShapeBase):
        """Structure shape implementation for testing"""

        def __init__(self, members_dict, serialization_names=None):
            self._members_dict = members_dict
            self._serialization_names = serialization_names or {}

        @property
        def type_name(self):
            return "structure"

        @property
        def members(self):
            return self._members_dict

        def get_serialization_name(self, member_name):
            return self._serialization_names.get(member_name, member_name)

    def test_write_data_item_shaped_basic_types(self):
        """Test write_data_item_shaped with basic scalar types"""

        # Test integer
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(42, self.SimpleShape("integer"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), 42)

        # Test long (same as integer in Python 3)
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(2**63, self.SimpleShape("long"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), 2**63)

        # Test float
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(3.14, self.SimpleShape("float"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertAlmostEqual(decoder.pop_next_data_item(), 3.14, places=5)

        # Test double
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(2.718281828, self.SimpleShape("double"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertAlmostEqual(decoder.pop_next_data_item(), 2.718281828, places=9)

        # Test boolean - True
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(True, self.SimpleShape("boolean"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertTrue(decoder.pop_next_data_item())

        # Test boolean - False
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(False, self.SimpleShape("boolean"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertFalse(decoder.pop_next_data_item())

        # Test string
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped("hello world", self.SimpleShape("string"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), "hello world")

        # Test empty string
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped("", self.SimpleShape("string"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), "")

        # Test blob
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(b"binary data", self.SimpleShape("blob"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), b"binary data")

        # Test empty blob
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(b"", self.SimpleShape("blob"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), b"")

    def test_write_data_item_shaped_list(self):
        """Test write_data_item_shaped with list types"""

        # Test list of integers
        encoder = AwsCborEncoder()
        int_list_shape = self.ListShape(self.SimpleShape("integer"))
        encoder.write_data_item_shaped([1, 2, 3, 4, 5], int_list_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), [1, 2, 3, 4, 5])

        # Test list of strings
        encoder = AwsCborEncoder()
        string_list_shape = self.ListShape(self.SimpleShape("string"))
        encoder.write_data_item_shaped(["a", "b", "c"], string_list_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), ["a", "b", "c"])

        # Test empty list
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped([], int_list_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), [])

        # Test nested list
        encoder = AwsCborEncoder()
        nested_list_shape = self.ListShape(self.ListShape(self.SimpleShape("integer")))
        encoder.write_data_item_shaped([[1, 2], [3, 4], [5]], nested_list_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), [[1, 2], [3, 4], [5]])

    def test_write_data_item_shaped_map(self):
        """Test write_data_item_shaped with map types"""

        # Test map with string keys and integer values
        encoder = AwsCborEncoder()
        map_shape = self.MapShape(self.SimpleShape("string"), self.SimpleShape("integer"))
        data = {"a": 1, "b": 2, "c": 3}
        encoder.write_data_item_shaped(data, map_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), data)

        # Test map with integer keys and string values
        encoder = AwsCborEncoder()
        map_shape = self.MapShape(self.SimpleShape("integer"), self.SimpleShape("string"))
        data = {1: "one", 2: "two", 3: "three"}
        encoder.write_data_item_shaped(data, map_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), data)

        # Test empty map
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped({}, map_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), {})

        # Test nested map
        encoder = AwsCborEncoder()
        nested_map_shape = self.MapShape(
            self.SimpleShape("string"),
            self.MapShape(self.SimpleShape("string"), self.SimpleShape("integer"))
        )
        data = {"outer1": {"inner1": 1, "inner2": 2}, "outer2": {"inner3": 3}}
        encoder.write_data_item_shaped(data, nested_map_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), data)

    def test_write_data_item_shaped_structure(self):
        """Test write_data_item_shaped with structure types"""

        # Test simple structure
        encoder = AwsCborEncoder()
        struct_shape = self.StructureShape({
            "id": self.SimpleShape("integer"),
            "name": self.SimpleShape("string"),
            "active": self.SimpleShape("boolean")
        })
        data = {"id": 123, "name": "Alice", "active": True}
        encoder.write_data_item_shaped(data, struct_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), data)

        # Test structure with None values (should be filtered out)
        encoder = AwsCborEncoder()
        data_with_none = {"id": 456, "name": None, "active": False}
        encoder.write_data_item_shaped(data_with_none, struct_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        # None values should be filtered out
        self.assertEqual(decoder.pop_next_data_item(), {"id": 456, "active": False})

        # Test structure with custom serialization names
        # Note: Custom serialization names may not be fully implemented yet in C binding
        # This test documents the expected behavior when it's implemented
        encoder = AwsCborEncoder()
        struct_shape_custom = self.StructureShape(
            {
                "user_id": self.SimpleShape("integer"),
                "user_name": self.SimpleShape("string")
            },
            serialization_names={"user_id": "UserId", "user_name": "UserName"}
        )
        data = {"user_id": 789, "user_name": "Bob"}
        encoder.write_data_item_shaped(data, struct_shape_custom)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        # For now, it uses the original names (not custom serialization names)
        # TODO: Update this test when custom serialization is implemented
        self.assertEqual(decoder.pop_next_data_item(), {"user_id": 789, "user_name": "Bob"})

    def test_write_data_item_shaped_nested_structure(self):
        """Test write_data_item_shaped with nested structures"""

        # Create nested structure: User with Address
        encoder = AwsCborEncoder()
        address_shape = self.StructureShape({
            "street": self.SimpleShape("string"),
            "city": self.SimpleShape("string"),
            "zip": self.SimpleShape("integer")
        })
        user_shape = self.StructureShape({
            "id": self.SimpleShape("integer"),
            "name": self.SimpleShape("string"),
            "address": address_shape
        })

        data = {
            "id": 1,
            "name": "Alice",
            "address": {
                "street": "123 Main St",
                "city": "Springfield",
                "zip": 12345
            }
        }
        encoder.write_data_item_shaped(data, user_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), data)

        # Test with None in nested structure
        encoder = AwsCborEncoder()
        data_with_none = {
            "id": 2,
            "name": "Bob",
            "address": {
                "street": "456 Elm St",
                "city": None,  # This should be filtered
                "zip": 67890
            }
        }
        encoder.write_data_item_shaped(data_with_none, user_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        expected = {
            "id": 2,
            "name": "Bob",
            "address": {
                "street": "456 Elm St",
                "zip": 67890
            }
        }
        self.assertEqual(decoder.pop_next_data_item(), expected)

    def test_write_data_item_shaped_structure_with_list(self):
        """Test write_data_item_shaped with structures containing lists"""

        encoder = AwsCborEncoder()
        struct_shape = self.StructureShape({
            "id": self.SimpleShape("integer"),
            "tags": self.ListShape(self.SimpleShape("string")),
            "scores": self.ListShape(self.SimpleShape("integer"))
        })

        data = {
            "id": 100,
            "tags": ["python", "aws", "cbor"],
            "scores": [85, 90, 95]
        }
        encoder.write_data_item_shaped(data, struct_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), data)

    def test_write_data_item_shaped_structure_with_map(self):
        """Test write_data_item_shaped with structures containing maps"""

        encoder = AwsCborEncoder()
        struct_shape = self.StructureShape({
            "id": self.SimpleShape("integer"),
            "metadata": self.MapShape(self.SimpleShape("string"), self.SimpleShape("string")),
            "counts": self.MapShape(self.SimpleShape("string"), self.SimpleShape("integer"))
        })

        data = {
            "id": 200,
            "metadata": {"author": "Alice", "version": "1.0"},
            "counts": {"views": 100, "likes": 50}
        }
        encoder.write_data_item_shaped(data, struct_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), data)

    def test_write_data_item_shaped_timestamp(self):
        """Test write_data_item_shaped with timestamp type"""

        # Test timestamp with converter
        encoder = AwsCborEncoder()
        timestamp_shape = self.SimpleShape("timestamp")

        # Create a mock datetime-like object
        class MockDateTime:
            def timestamp(self):
                return 1609459200.0  # 2021-01-01 00:00:00 UTC

        mock_dt = MockDateTime()

        # Converter function
        def timestamp_converter(dt):
            return dt.timestamp()

        encoder.write_data_item_shaped(mock_dt, timestamp_shape, timestamp_converter)

        # Decode and verify it's encoded as epoch time with tag
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        # Should have tag 1 followed by the float value
        self.assertEqual(decoder.peek_next_type(), AwsCborType.Tag)
        tag_id = decoder.pop_next_tag_val()
        self.assertEqual(tag_id, 1)
        timestamp_value = decoder.pop_next_data_item()
        self.assertAlmostEqual(timestamp_value, 1609459200.0, places=5)

        # Test timestamp without converter (already numeric)
        # When converter is None, pass a simple converter that returns the value as-is
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(1609459200.5, timestamp_shape, lambda x: x)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.peek_next_type(), AwsCborType.Tag)
        tag_id = decoder.pop_next_tag_val()
        self.assertEqual(tag_id, 1)
        timestamp_value = decoder.pop_next_data_item()
        self.assertAlmostEqual(timestamp_value, 1609459200.5, places=5)

    def test_write_data_item_shaped_complex_nested(self):
        """Test write_data_item_shaped with complex nested structures"""

        encoder = AwsCborEncoder()

        # Create a complex shape: Organization with departments, each with employees
        employee_shape = self.StructureShape({
            "id": self.SimpleShape("integer"),
            "name": self.SimpleShape("string"),
            "email": self.SimpleShape("string"),
            "skills": self.ListShape(self.SimpleShape("string"))
        })

        department_shape = self.StructureShape({
            "name": self.SimpleShape("string"),
            "budget": self.SimpleShape("integer"),
            "employees": self.ListShape(employee_shape)
        })

        org_shape = self.StructureShape({
            "org_name": self.SimpleShape("string"),
            "founded": self.SimpleShape("integer"),
            "departments": self.ListShape(department_shape),
            "metadata": self.MapShape(self.SimpleShape("string"), self.SimpleShape("string"))
        })

        data = {
            "org_name": "TechCorp",
            "founded": 2020,
            "departments": [
                {
                    "name": "Engineering",
                    "budget": 1000000,
                    "employees": [
                        {
                            "id": 1,
                            "name": "Alice",
                            "email": "alice@techcorp.com",
                            "skills": ["Python", "Go", "AWS"]
                        },
                        {
                            "id": 2,
                            "name": "Bob",
                            "email": "bob@techcorp.com",
                            "skills": ["Java", "Kubernetes"]
                        }
                    ]
                },
                {
                    "name": "Sales",
                    "budget": 500000,
                    "employees": [
                        {
                            "id": 3,
                            "name": "Charlie",
                            "email": "charlie@techcorp.com",
                            "skills": ["Negotiation", "CRM"]
                        }
                    ]
                }
            ],
            "metadata": {"industry": "Technology", "location": "Seattle"}
        }

        encoder.write_data_item_shaped(data, org_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        decoded = decoder.pop_next_data_item()
        self.assertEqual(decoded, data)

    def test_write_data_item_shaped_empty_collections(self):
        """Test write_data_item_shaped with empty collections"""

        # Empty structure
        encoder = AwsCborEncoder()
        struct_shape = self.StructureShape({})
        encoder.write_data_item_shaped({}, struct_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), {})

        # Structure with all None values (should result in empty map)
        encoder = AwsCborEncoder()
        struct_shape = self.StructureShape({
            "a": self.SimpleShape("string"),
            "b": self.SimpleShape("integer")
        })
        encoder.write_data_item_shaped({"a": None, "b": None}, struct_shape)
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), {})

    def test_write_data_item_shaped_special_values(self):
        """Test write_data_item_shaped with special float values"""
        import math

        # Test positive infinity
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(float('inf'), self.SimpleShape("float"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        result = decoder.pop_next_data_item()
        self.assertTrue(math.isinf(result) and result > 0)

        # Test negative infinity
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(float('-inf'), self.SimpleShape("double"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        result = decoder.pop_next_data_item()
        self.assertTrue(math.isinf(result) and result < 0)

        # Test NaN
        encoder = AwsCborEncoder()
        encoder.write_data_item_shaped(float('nan'), self.SimpleShape("float"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        result = decoder.pop_next_data_item()
        self.assertTrue(math.isnan(result))

    def test_write_data_item_shaped_large_numbers(self):
        """Test write_data_item_shaped with large numbers"""

        # Test large positive integer
        encoder = AwsCborEncoder()
        large_int = 2**63 - 1
        encoder.write_data_item_shaped(large_int, self.SimpleShape("long"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), large_int)

        # Test large negative integer
        encoder = AwsCborEncoder()
        large_neg = -2**63
        encoder.write_data_item_shaped(large_neg, self.SimpleShape("long"))
        decoder = AwsCborDecoder(encoder.get_encoded_data())
        self.assertEqual(decoder.pop_next_data_item(), large_neg)
