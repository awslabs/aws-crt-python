"""
Cross-platform library for `awscrt`.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt._c_lib_importer import _awscrt


def get_cpu_group_count() -> int:
    """
    Returns number of processor groups on the system.

    Useful for working with non-uniform memory access (NUMA) nodes.
    """
    return _awscrt.get_cpu_group_count()


def get_cpu_count_for_group(group_idx: int) -> int:
    """
    Returns number of processors in a given group.
    """
    return _awscrt.get_cpu_count_for_group(group_idx)
