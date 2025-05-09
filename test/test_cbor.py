# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from test import NativeResourceTest
from awscrt.cbor import *
import json
import struct
import os


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
