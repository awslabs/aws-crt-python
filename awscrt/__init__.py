# Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

from sys import version_info
from weakref import WeakSet

__all__ = ['io', 'mqtt', 'crypto', 'http']

class NativeResource(object):
    """
    Base for classes that bind to a native type.
    _binding is a python capsule referencing the native object.

    Note to developers: If NativeResource B depends on the existence of NativeResource A,
    have B's native code Py_INCREF/DECREF A's python class. This ensures that A will not be destroyed before B.
    If we simply had python class B referencing A, and the GC decided to clean up both, it might destroy A before B.

    Class Attributes:
        track_lifetime  Set True to track lifetime of all NativeResources (useful for debugging)
        living          WeakSet of all living NativeResources (only updated when `track_lifetime` is True).
    """

    track_lifetime = False
    living = WeakSet()

    __slots__ = ('_binding', '__weakref__')

    def __init__(self):
        if NativeResource.track_lifetime:
            NativeResource.living.add(self)


def isinstance_str(x):
    """
    Python 2/3 compatible way to check isinstance(x, str).
    """
    if version_info[0] == 2:
        return isinstance(x, basestring)
    return isinstance(x, str)
