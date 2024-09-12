# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.


from test import NativeResourceTest
from awscrt import checksums
import unittest
import sys


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

    def test_crc32_large_buffer(self):
        # stress test gil optimization for 32 bit architecture which cannot handle huge buffer
        large_buffer = bytes(25 * 2**20)
        val = checksums.crc32(large_buffer)
        self.assertEqual(0x72103906, val)

    def test_crc32_huge_buffer(self):
        # stress the internal logic that handles buffers larger than C's INT_MAX
        if sys.platform.startswith('freebsd'):
            # Skip this test for freebsd, as it simply crashes instead of raising exception in this case
            raise unittest.SkipTest('Skip this test for freebsd')
        try:
            INT_MAX = 2**32 - 1
            huge_buffer = bytes(INT_MAX + 5)
        except (MemoryError, OverflowError):
            raise unittest.SkipTest('Machine cant allocate giant buffer for giant buffer test')
        val = checksums.crc32(huge_buffer)
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

    def test_crc32c_large_buffer(self):
        # stress test gil optimization for 32 bit architecture which cannot handle huge buffer
        large_buffer = bytes(25 * 2**20)
        val = checksums.crc32c(large_buffer)
        self.assertEqual(0xfb5b991d, val)

    def test_crc32c_huge_buffer(self):
        if sys.platform.startswith('freebsd'):
            # Skip this test for freebsd, as it simply crashes instead of raising exception in this case
            raise unittest.SkipTest('Skip this test for freebsd')
        try:
            INT_MAX = 2**32 - 1
            huge_buffer = bytes(INT_MAX + 5)
        except BaseException:
            raise unittest.SkipTest('Machine cant allocate giant buffer for giant buffer test')
        val = checksums.crc32c(huge_buffer)
        self.assertEqual(0x572a7c8a, val)

    def test_crc64nvme_zeros_one_shot(self):
        output = checksums.crc64nvme(bytes(32))
        expected = 0xcf3473434d4ecf3b
        self.assertEqual(expected, output)

    def test_crc64nvme_zeros_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc64nvme(bytes(1), output)
        expected = 0xcf3473434d4ecf3b
        self.assertEqual(expected, output)

    def test_crc64nvme_values_one_shot(self):
        output = checksums.crc64nvme(''.join(chr(i) for i in range(32)))
        expected = 0xb9f0b46aac3b555f
        self.assertEqual(expected, output)

    def test_crc64nvme_values_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc64nvme(chr(i), output)
        expected = 0xb9f0b46aac3b555f
        self.assertEqual(expected, output)

    def test_crc64nvme_large_buffer(self):
        # stress test gil optimization for 32 bit architecture which cannot handle huge buffer
        large_buffer = bytes(25 * 2**20)
        val = checksums.crc64nvme(large_buffer)
        self.assertEqual(0x5b6f5045463ca45e, val)

    def test_crc64nvme_huge_buffer(self):
        if sys.platform.startswith('freebsd'):
            # Skip this test for freebsd, as it simply crashes instead of raising exception in this case
            raise unittest.SkipTest('Skip this test for freebsd')
        try:
            INT_MAX = 2**32 - 1
            huge_buffer = bytes(INT_MAX + 5)
        except BaseException:
            raise unittest.SkipTest('Machine cant allocate giant buffer for giant buffer test')
        val = checksums.crc64nvme(huge_buffer)
        self.assertEqual(0x2645c28052b1fbb0, val)


if __name__ == '__main__':
    unittest.main()
