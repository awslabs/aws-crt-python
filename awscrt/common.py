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

class SystemEnvironment:

    def __init__(self):
        self._env = _awscrt.load_system_environment()

    def is_ec2_nitro_instance(self) -> bool:    
        return _awscrt.is_env_ec2(self._env)
    
    def get_ec2_instance_type(self) -> str:
        return _awscrt.get_ec2_instance_type(self._env)
    