# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from test import NativeResourceTest
from awscrt.cbor import *


class TestCBOR(NativeResourceTest):
    def test_cbor_encode_decode_int(self):
        encoder = AwsCborEncoder()
        try:
            # Overflow
            encoder.write_int(2**64)
        except OverflowError as e:
            self.assertIsNotNone(e)
        else:
            self.assertTrue(False)
        try:
            # pass float instead of int
            encoder.write_int(1.1)
        except ValueError as e:
            self.assertIsNotNone(e)
        else:
            self.assertTrue(False)

        val_to_write = [-100, 100, 2**64 - 1, -2**64]
        for val in val_to_write:
            encoder.write_int(val)

        decoder = AwsCborDecoder(encoder.get_encoded_data())
        try:
            val = decoder.pop_next_unsigned_int()
        except RuntimeError as e:
            self.assertIsNotNone(e)
        else:
            self.assertTrue(False)

        for val in val_to_write:
            t = decoder.pop_next_numeric()
            self.assertEqual(t, val)

        self.assertEqual(decoder.get_remaining_bytes_len(), 0)

    def test_cbor_encode_decode_float(self):
        encoder = AwsCborEncoder()
        val_to_write = [-100.12, -100, 100, 2**64 - 1, -2**64, 18446744073709551616.0]
        for val in val_to_write:
            encoder.write_float(val)

        decoder = AwsCborDecoder(encoder.get_encoded_data())

        for val in val_to_write:
            t = decoder.pop_next_numeric()
            self.assertEqual(t, val)

        self.assertEqual(decoder.get_remaining_bytes_len(), 0)

    def test_cbor_encode_decode_data_item(self):
        encoder = AwsCborEncoder()
        val_to_write = {
            "mytest": b"write_test",
            b"test_more": {
                "another": 123,
                b"more": [1, 2, 3]
            },
            2: {
                2.3: ["a", "b", "c"]
            }
        }
        encoder.write_data_item(val_to_write)

        decoder = AwsCborDecoder(encoder.get_encoded_data())

        t = decoder.pop_next_data_item()
        self.assertEqual(val_to_write, t)
