# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

from awscrt import NativeResource
import gc
import sys
import types
import unittest


class NativeResourceTest(unittest.TestCase):
    """
    Test fixture asserts there are no living NativeResources when a test completes.
    """

    def setUp(self):
        NativeResource._track_lifetime = True

    def tearDown(self):
        gc.collect()

        # Print out debugging info on leaking resources
        if NativeResource._living:
            print('Leaking NativeResources:')
            for i in NativeResource._living:
                print('-', i)

                # getrefcount(i) returns 4+ here, but 2 of those are due to debugging.
                # Don't show:
                # - 1 for WeakSet iterator due to this for-loop.
                # - 1 for getrefcount(i)'s reference.
                # But do show:
                # - 1 for item's self-reference.
                # - the rest are what's causing this leak.
                refcount = sys.getrefcount(i) - 2

                # The act of iterating a WeakSet creates a reference. Don't show that.
                referrers = gc.get_referrers(i)
                for r in referrers:
                    if isinstance(r, types.FrameType) and '_weakrefset.py' in str(r):
                        referrers.remove(r)
                        break

                print('  sys.getrefcount():', refcount)
                print('  gc.referrers():', len(referrers))
                for r in referrers:
                    print('  -', r)

        self.assertEqual(0, len(NativeResource._living))
