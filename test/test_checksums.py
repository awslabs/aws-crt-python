# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.


from test import NativeResourceTest
from awscrt import checksums
import unittest


class TestChecksums(NativeResourceTest):

    def test_crc32_zeros_one_shot(self):
        output = checksums.crc32(bytes(32))
        expected = 0x190A55AD
        self.assertEqual(expected, output)

    def test_crc32_zeros_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc32(bytes(1), output)
        expected = 0x190A55AD
        self.assertEqual(expected, output)

    def test_crc32_values_one_shot(self):
        output = checksums.crc32(''.join(chr(i) for i in range(32)))
        expected = 0x91267E8A
        self.assertEqual(expected, output)

    def test_crc32_values_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc32(chr(i), output)
        expected = 0x91267E8A
        self.assertEqual(expected, output)

# stress the internal logic that handles buffers larger than C's INT_MAX
    def test_crc32_large_buffer(self):
        try:
            INT_MAX = 2**32 - 1
            giant_buffer = bytes(INT_MAX + 5)
        except MemoryError:
            raise unittest.SkipTest('Machine cant allocate giant buffer for giant buffer test')
        val = checksums.crc32(giant_buffer)
        self.assertEqual(0xc622f71d, val)

    def test_crc32c_zeros_one_shot(self):
        output = checksums.crc32c(bytes(32))
        expected = 0x8A9136AA
        self.assertEqual(expected, output)

    def test_crc32c_zeros_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc32c(bytes(1), output)
        expected = 0x8A9136AA
        self.assertEqual(expected, output)

    def test_crc32c_values_one_shot(self):
        output = checksums.crc32c(''.join(chr(i) for i in range(32)))
        expected = 0x46DD794E
        self.assertEqual(expected, output)

    def test_crc32c_values_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc32c(chr(i), output)
        expected = 0x46DD794E
        self.assertEqual(expected, output)

# stress the internal logic that handles buffers larger than C's INT_MAX
    def test_crc32c_large_buffer(self):
        try:
            INT_MAX = 2**32 - 1
            giant_buffer = bytes(INT_MAX + 5)
        except MemoryError:
            raise unittest.SkipTest('Machine cant allocate giant buffer for giant buffer test')
        val = checksums.crc32c(giant_buffer)
        self.assertEqual(0x572a7c8a, val)


if __name__ == '__main__':
    unittest.main()
