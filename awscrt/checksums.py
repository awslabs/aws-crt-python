# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt


def crc32(input: bytes, previous_crc32: int) -> int:
    """
    update a crc32 output
    """
    return _awscrt.checksums_crc32(input, previous_crc32)


def crc32c(input: bytes, previous_crc32c: int) -> int:
    """
    update a crc32c output
    """
    return _awscrt.checksums_crc32c(input, previous_crc32c)
