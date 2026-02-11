# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.


from test import NativeResourceTest
from awscrt import checksums
from awscrt.checksums import XXHash
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
        expected = 0xb9d9d4a8492cbd7f
        self.assertEqual(expected, output)

    def test_crc64nvme_values_iterated(self):
        output = 0
        for i in range(32):
            output = checksums.crc64nvme(chr(i), output)
        expected = 0xb9d9d4a8492cbd7f
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

    def _test_combine_helper(self, checksum_fn, combine_fn):
        """Helper method to test checksum combine functions with various scenarios."""

        # Test 1: Basic combine of two blocks
        data1 = b"Hello, "
        data2 = b"World!"

        crc1 = checksum_fn(data1)
        crc2 = checksum_fn(data2)
        combined = combine_fn(crc1, crc2, len(data2))
        expected = checksum_fn(data1 + data2)

        self.assertEqual(expected, combined)

        # Test 2: Empty second block
        data1 = b"Hello, World!"
        data2 = b""

        crc1 = checksum_fn(data1)
        crc2 = checksum_fn(data2)
        combined = combine_fn(crc1, crc2, len(data2))

        self.assertEqual(crc1, combined)

        # Test 3: Multiple blocks
        data1 = b"The quick "
        data2 = b"brown fox "
        data3 = b"jumps over the lazy dog"

        crc1 = checksum_fn(data1)
        crc2 = checksum_fn(data2)
        crc3 = checksum_fn(data3)

        combined_12 = combine_fn(crc1, crc2, len(data2))
        combined_123 = combine_fn(combined_12, crc3, len(data3))
        expected = checksum_fn(data1 + data2 + data3)

        self.assertEqual(expected, combined_123)

        # Test 4: Large blocks
        data1 = bytes(1024)
        data2 = bytes(range(256)) * 4

        crc1 = checksum_fn(data1)
        crc2 = checksum_fn(data2)
        combined = combine_fn(crc1, crc2, len(data2))
        expected = checksum_fn(data1 + data2)

        self.assertEqual(expected, combined)

    def test_crc32_combine(self):
        """Test CRC32 combine function."""
        self._test_combine_helper(checksums.crc32, checksums.combine_crc32)

    def test_crc32c_combine(self):
        """Test CRC32C combine function."""
        self._test_combine_helper(checksums.crc32c, checksums.combine_crc32c)

    def test_crc64nvme_combine(self):
        """Test CRC64-NVME combine function."""
        self._test_combine_helper(checksums.crc64nvme, checksums.combine_crc64nvme)

    def test_combine_invalid_inputs(self):
        """Test that combine functions raise ValueError for invalid inputs."""
        # Test invalid values (should fail for all algorithms)
        for combine_fn in [checksums.combine_crc32, checksums.combine_crc32c, checksums.combine_crc64nvme]:
            with self.assertRaises(ValueError) as context:
                combine_fn(-1, 0, 0)
            self.assertIn("not a valid unsigned", str(context.exception))

            with self.assertRaises(ValueError) as context:
                combine_fn(0, 0, -1)
            self.assertIn("not a valid unsigned", str(context.exception))

        # Test that valid inputs don't raise exceptions
        for combine_fn in [checksums.combine_crc32, checksums.combine_crc32c, checksums.combine_crc64nvme]:
            # This should not raise any exception
            result = combine_fn(0, 0, 0)
            # Result should be an integer
            self.assertIsInstance(result, int)

    def test_xxhash64_piping(self):
        """Test xxhash64 piping from native side"""
        data = b"Hello world"

        out = XXHash.compute_xxhash64(data)

        expected = bytes([0xc5, 0x00, 0xb0, 0xc9, 0x12, 0xb3, 0x76, 0xd8])

        self.assertEqual(out, expected)

        hash = XXHash.new_xxhash64()
        hash.update(data)
        out2 = hash.finalize()
        self.assertEqual(out2, expected)

    def test_xxhash3_64_piping(self):
        """Test xxhash3_64 piping from native side"""
        data = b"Hello world"

        out = XXHash.compute_xxhash3_64(data)

        expected = bytes([0xb6, 0xac, 0xb9, 0xd8, 0x4a, 0x38, 0xff, 0x74])

        self.assertEqual(out, expected)

        hash = XXHash.new_xxhash3_64()
        hash.update(data)
        out2 = hash.finalize()
        self.assertEqual(out2, expected)

    def test_xxhash3_128_piping(self):
        """Test xxhash3_128 piping from native side"""
        data = b"Hello world"

        out = XXHash.compute_xxhash3_128(data)

        expected = bytes([0x73, 0x51, 0xf8, 0x98, 0x12, 0xf9, 0x73, 0x82,
                          0xb9, 0x1d, 0x05, 0xb3, 0x1e, 0x04, 0xdd, 0x7f])

        self.assertEqual(out, expected)

        hash = XXHash.new_xxhash3_128()
        hash.update(data)
        out2 = hash.finalize()
        self.assertEqual(out2, expected)


if __name__ == '__main__':
    unittest.main()
