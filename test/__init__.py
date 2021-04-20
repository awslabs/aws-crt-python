# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt import NativeResource
import gc
import inspect
import sys
import time
import types
import unittest
import tempfile
import math
import os
import shutil

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
                        _printobj('  -', inspect.getframeinfo(r))
                    else:
                        _printobj('  -', r)

        self.assertEqual(0, len(NativeResource._living))


class FileCreator(object):
    def __init__(self):
        self.rootdir = tempfile.mkdtemp()

    def remove_all(self):
        shutil.rmtree(self.rootdir)

    def create_file(self, filename, contents, mode='w'):
        """Creates a file in a tmpdir
        ``filename`` should be a relative path, e.g. "foo/bar/baz.txt"
        It will be translated into a full path in a tmp dir.
        ``mode`` is the mode the file should be opened either as ``w`` or
        `wb``.
        Returns the full path to the file.
        """
        full_path = os.path.join(self.rootdir, filename)
        if not os.path.isdir(os.path.dirname(full_path)):
            os.makedirs(os.path.dirname(full_path))
        with open(full_path, mode) as f:
            f.write(contents)
        return full_path

    def create_file_with_size(self, filename, filesize):
        filename = self.create_file(filename, contents='')
        chunksize = 8192
        with open(filename, 'wb') as f:
            for i in range(int(math.ceil(filesize / float(chunksize)))):
                f.write(b'a' * chunksize)
        return filename

    def append_file(self, filename, contents):
        """Append contents to a file
        ``filename`` should be a relative path, e.g. "foo/bar/baz.txt"
        It will be translated into a full path in a tmp dir.
        Returns the full path to the file.
        """
        full_path = os.path.join(self.rootdir, filename)
        if not os.path.isdir(os.path.dirname(full_path)):
            os.makedirs(os.path.dirname(full_path))
        with open(full_path, 'a') as f:
            f.write(contents)
        return full_path

    def full_path(self, filename):
        """Translate relative path to full path in temp dir.
        f.full_path('foo/bar.txt') -> /tmp/asdfasd/foo/bar.txt
        """
        return os.path.join(self.rootdir, filename)
