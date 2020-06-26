# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from sys import version_info
from weakref import WeakSet

__all__ = [
    'auth',
    'crypto',
    'http',
    'io',
    'mqtt',
]


class NativeResource(object):
    """
    Base for classes that bind to a native type.
    _binding is a python capsule referencing the native object.

    Note to developers: If NativeResource B depends on the existence of NativeResource A,
    have B's native code Py_INCREF/DECREF A's python class. This ensures that A will not be destroyed before B.
    If we simply had python class B referencing A, and the GC decided to clean up both, it might destroy A before B.
    """

    # For tracking live NativeResources in tests/debug.
    # Note that WeakSet can accurately report if 0 objects exist, but iteration isn't 100% thread-safe.
    _track_lifetime = False
    _living = WeakSet()

    __slots__ = ('_binding', '__weakref__')

    def __init__(self):
        if NativeResource._track_lifetime:
            NativeResource._living.add(self)


def isinstance_str(x):
    """
    Python 2/3 compatible way to check isinstance(x, str).
    """
    if version_info[0] == 2:
        return isinstance(x, basestring)
    return isinstance(x, str)
