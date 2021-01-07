"""
Cross-platform library for `awscrt`.
"""
import _awscrt
from typing import List


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


def get_cpu_ids_for_group(group_idx: int) -> List[int]:
    """
    Returns list of processor IDs for a given group.
    """
    return _awscrt.get_cpu_ids_for_group(group_idx)
