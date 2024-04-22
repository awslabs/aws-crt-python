# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from test import NativeResourceTest
from awscrt.cbor import *


class TestCBOR(NativeResourceTest):
    def test_cbor_encode_decode_int(self):
        encoder = AwsCborEncoder()
        try:
            # pass float instead of int
            encoder.write_int(1.1)
        except AssertionError as e:
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
            t = decoder.pop_next_numeric()
            self.assertEqual(t, val)

        self.assertEqual(decoder.get_remaining_bytes_len(), 0)

    def test_cbor_encode_decode_data_item(self):
        encoder = AwsCborEncoder()
        numerics = [-100.12, 100.0, -100, 100, 2**64 - 1, -2**64, 18446744073709551616.0]
        another_map = {
            "bignum": 2**65,
            "negative bignum": -2**75,
            2**65: [1, 2, 3],
            -2**65: [1, ["2", b"3"], {"most complicated": numerics}, 2**65, -2**75]
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
        }
        encoder.write_data_item_2(val_to_write)

        decoder = AwsCborDecoder(encoder.get_encoded_data())

        # Temp val only for easier to debug.
        t = decoder.pop_next_data_item()
        print(t)
        print(val_to_write)
        self.assertEqual(val_to_write, t)