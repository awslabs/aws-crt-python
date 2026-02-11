# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from awscrt import NativeResource
from typing import Union


def crc32(input: bytes, previous_crc32: int = 0) -> int:
    """
    Perform a CRC32 (Ethernet, gzip) computation.

    If continuing to update a running CRC, pass its value into `previous_crc32`.
    Returns an unsigned 32-bit integer.
    """
    return _awscrt.checksums_crc32(input, previous_crc32)


def crc32c(input: bytes, previous_crc32c: int = 0) -> int:
    """
    Perform a Castagnoli CRC32c (iSCSI) computation.
    If continuing to update a running CRC, pass its value into `previous_crc32c`.
    Returns an unsigned 32-bit integer.
    """
    return _awscrt.checksums_crc32c(input, previous_crc32c)


def crc64nvme(input: bytes, previous_crc64nvme: int = 0) -> int:
    """
    Perform a CRC64 NVME computation.
    If continuing to update a running CRC, pass its value into `previous_crc64nvme`.
    Returns an unsigned 64-bit integer.
    """
    return _awscrt.checksums_crc64nvme(input, previous_crc64nvme)


def combine_crc32(crc32_result1: int, crc32_result2: int, data_length2: int) -> int:
    """
    Combine two CRC32 (Ethernet, gzip) checksums computed over separate data blocks.

    This is equivalent to computing the CRC32 of the concatenated data blocks without
    having to re-scan the data.

    Given:
        crc1 = CRC32(data_block_A)
        crc2 = CRC32(data_block_B)

    This function computes:
        result = CRC32(data_block_A || data_block_B)

    Args:
        crc32_result1: The CRC32 checksum of the first data block
        crc32_result2: The CRC32 checksum of the second data block
        data_length2: The length (in bytes) of the original data that produced crc32_result2.
                      This is NOT the size of the checksum (which is always 4 bytes),
                      but rather the size of the data block that was checksummed.

    Returns:
        The combined CRC32 checksum as if computed over the concatenated data
    """
    return _awscrt.checksums_crc32_combine(crc32_result1, crc32_result2, data_length2)


def combine_crc32c(crc32c_result1: int, crc32c_result2: int, data_length2: int) -> int:
    """
    Combine two CRC32C (Castagnoli, iSCSI) checksums computed over separate data blocks.

    This is equivalent to computing the CRC32C of the concatenated data blocks without
    having to re-scan the data.

    Given:
        crc1 = CRC32C(data_block_A)
        crc2 = CRC32C(data_block_B)

    This function computes:
        result = CRC32C(data_block_A || data_block_B)

    Args:
        crc32c_result1: The CRC32C checksum of the first data block
        crc32c_result2: The CRC32C checksum of the second data block
        data_length2: The length (in bytes) of the original data that produced crc32c_result2.
                      This is NOT the size of the checksum (which is always 4 bytes),
                      but rather the size of the data block that was checksummed.

    Returns:
        The combined CRC32C checksum as if computed over the concatenated data
    """
    return _awscrt.checksums_crc32c_combine(crc32c_result1, crc32c_result2, data_length2)


def combine_crc64nvme(crc64nvme_result1: int, crc64nvme_result2: int, data_length2: int) -> int:
    """
    Combine two CRC64-NVME (CRC64-Rocksoft) checksums computed over separate data blocks.

    This is equivalent to computing the CRC64-NVME of the concatenated data blocks without
    having to re-scan the data.

    Given:
        crc1 = CRC64_NVME(data_block_A)
        crc2 = CRC64_NVME(data_block_B)

    This function computes:
        result = CRC64_NVME(data_block_A || data_block_B)

    Args:
        crc64nvme_result1: The CRC64-NVME checksum of the first data block
        crc64nvme_result2: The CRC64-NVME checksum of the second data block
        data_length2: The length (in bytes) of the original data that produced crc64nvme_result2.
                      This is NOT the size of the checksum (which is always 8 bytes),
                      but rather the size of the data block that was checksummed.

    Returns:
        The combined CRC64-NVME checksum as if computed over the concatenated data
    """
    return _awscrt.checksums_crc64nvme_combine(crc64nvme_result1, crc64nvme_result2, data_length2)


class XXHash(NativeResource):
    def __init__(self, binding):
        super().__init__()
        self._binding = binding

    @staticmethod
    def new_xxhash64(seed: int = 0) -> 'XXHash':
        """
        Generates a new instance of XXHash64 hash.
        """
        return XXHash(binding=_awscrt.xxhash64_new(seed))

    @staticmethod
    def new_xxhash3_64(seed: int = 0) -> 'XXHash':
        """
        Generates a new instance of XXHash3_64 hash.
        """
        return XXHash(binding=_awscrt.xxhash3_64_new(seed))

    @staticmethod
    def new_xxhash3_128(seed: int = 0) -> 'XXHash':
        """
        Generates a new instance of XXHash3_128 hash.
        """
        return XXHash(binding=_awscrt.xxhash3_128_new(seed))

    @staticmethod
    def compute_xxhash64(input: Union[bytes, bytearray, memoryview], seed: int = 0) -> bytes:
        """
        One-shot compute of xxhash64
        """
        return _awscrt.xxhash64_compute(input, seed)

    @staticmethod
    def compute_xxhash3_64(input: Union[bytes, bytearray, memoryview], seed: int = 0) -> bytes:
        """
        One-shot compute of xxhash3_64
        """
        return _awscrt.xxhash3_64_compute(input, seed)

    @staticmethod
    def compute_xxhash3_128(input: Union[bytes, bytearray, memoryview], seed: int = 0) -> bytes:
        """
        One-shot compute of xxhash3_128
        """
        return _awscrt.xxhash3_128_compute(input, seed)

    def update(self, input: Union[bytes, bytearray, memoryview]):
        """
        Updates hash with the provided input.
        """
        _awscrt.xxhash_update(self._binding, input)

    def finalize(self) -> bytes:
        """
        Finalizes hash.
        """
        return _awscrt.xxhash_finalize(self._binding, input)
