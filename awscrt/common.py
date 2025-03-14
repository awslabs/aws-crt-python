"""
Cross-platform library for `awscrt`.
"""
import _awscrt


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


def join_all_native_threads(*, timeout_sec: float = -1.0) -> bool:
    """
    Waits for all native threads to complete their join call.

    This can only be safely called from the main thread.
    This call may be required for native memory usage to reach zero.

    Args:
        timeout_sec (float): Number of seconds to wait before a timeout exception is raised.
            By default the wait is unbounded.

    Returns:
        bool: Returns whether threads could be joined before the timeout.
    """
    return _awscrt.thread_join_all_managed(timeout_sec)
