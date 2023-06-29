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


def install_crash_handler():
    """
        Registers a crash handler that will generate crash dumps in the event of a fatal error.
    """
    _awscrt.install_crash_handler()
