# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.


from test import NativeResourceTest
from awscrt import checksums


class TestChecksums(NativeResourceTest):

    def test_crc32_zeros_one_shot(self):
        output = checksums.crc32(''.join(chr(i) for i in [0] * 32), 0)
        expected = 0x190A55AD
        self.assertEqual(expected, output)

    def test_crc32_zeros_iterated(self):
        output = 0
        for i in ''.join(chr(i) for i in [0] * 32):
            output = checksums.crc32(i, output)
        expected = 0x190A55AD
        self.assertEqual(expected, output)

    def test_crc32_values_one_shot(self):
        output = checksums.crc32(''.join(chr(i) for i in range(32)), 0)
        expected = 0x91267E8A
        self.assertEqual(expected, output)

    def test_crc32_values_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc32(chr(i), output)
        expected = 0x91267E8A
        self.assertEqual(expected, output)

    def test_crc32c_zeros_one_shot(self):
        output = checksums.crc32c(''.join(chr(i) for i in [0] * 32), 0)
        expected = 0x8A9136AA
        self.assertEqual(expected, output)

    def test_crc32c_zeros_iterated(self):
        output = 0
        for i in ''.join(chr(i) for i in [0] * 32):
            output = checksums.crc32c(i, output)
        expected = 0x8A9136AA
        self.assertEqual(expected, output)

    def test_crc32c_values_one_shot(self):
        output = checksums.crc32c(''.join(chr(i) for i in range(32)), 0)
        expected = 0x46DD794E
        self.assertEqual(expected, output)

    def test_crc32c_values_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc32c(chr(i), output)
        expected = 0x46DD794E
        self.assertEqual(expected, output)


if __name__ == '__main__':
    unittest.main()
