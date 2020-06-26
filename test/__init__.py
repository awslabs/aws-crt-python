# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from __future__ import print_function
from awscrt import NativeResource
import gc
import inspect
import sys
import time
import types
import unittest

TIMEOUT = 10.0


class NativeResourceTest(unittest.TestCase):
    """
    Test fixture asserts there are no living NativeResources when a test completes.
    """

    def setUp(self):
        NativeResource._track_lifetime = True

    def tearDown(self):
        gc.collect()

        # Native resources might need a few more ticks to finish cleaning themselves up.
        wait_until = time.time() + TIMEOUT
        while NativeResource._living and time.time() < wait_until:
            time.sleep(0.1)

        # Print out debugging info on leaking resources
        if NativeResource._living:

            def _printobj(prefix, obj):
                s = str(obj)
                if len(s) > 1000:
                    s = s[:1000] + '...TRUNCATED total-len=' + str(len(s))
                print(prefix, obj)

            print('Leaking NativeResources:')
            for i in NativeResource._living:
                _printobj('-', i)

                # getrefcount(i) returns 4+ here, but 2 of those are due to debugging.
                # Don't show:
                # - 1 for WeakSet iterator due to this for-loop.
                # - 1 for getrefcount(i)'s reference.
                # But do show:
                # - 1 for item's self-reference.
                # - the rest are what's causing this leak.
                refcount = sys.getrefcount(i) - 2

                # Gather list of referrers, but don't show those created by the act of iterating the WeakSet
                referrers = []
                for r in gc.get_referrers(i):
                    if isinstance(r, types.FrameType):
                        frameinfo = inspect.getframeinfo(r)
                        our_fault = (frameinfo.filename.endswith('_weakrefset.py') or
                                     frameinfo.filename.endswith('test/__init__.py'))
                        if our_fault:
                            continue

                    referrers.append(r)

                print('  sys.getrefcount():', refcount)
                print('  gc.referrers():', len(referrers))
                for r in referrers:
                    if isinstance(r, types.FrameType):
                        print('  -', inspect.getframeinfo(r))
                    else:
                        _printobj('  -', r)

        self.assertEqual(0, len(NativeResource._living))
