# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.


from test import NativeResourceTest
from awscrt.crypto import Hash
from awscrt.io import TlsCipherPref
import unittest


class TestCredentials(NativeResourceTest):

    def test_sha256_empty(self):
        h = Hash.sha256_new()
        digest = h.digest()
        expected = b'\xe3\xb0\xc4\x42\x98\xfc\x1c\x14\x9a\xfb\xf4\xc8\x99\x6f\xb9\x24\x27\xae\x41\xe4\x64\x9b\x93\x4c\xa4\x95\x99\x1b\x78\x52\xb8\x55'
        self.assertEqual(expected, digest)

    def test_sha256_one_shot(self):
        h = Hash.sha256_new()
        h.update('abc')
        digest = h.digest()
        expected = b'\xba\x78\x16\xbf\x8f\x01\xcf\xea\x41\x41\x40\xde\x5d\xae\x22\x23\xb0\x03\x61\xa3\x96\x17\x7a\x9c\xb4\x10\xff\x61\xf2\x00\x15\xad'
        self.assertEqual(expected, digest)

    def test_sha256_iterated(self):
        h = Hash.sha256_new()
        h.update('a')
        h.update('b')
        h.update('c')
        digest = h.digest()
        expected = b'\xba\x78\x16\xbf\x8f\x01\xcf\xea\x41\x41\x40\xde\x5d\xae\x22\x23\xb0\x03\x61\xa3\x96\x17\x7a\x9c\xb4\x10\xff\x61\xf2\x00\x15\xad'
        self.assertEqual(expected, digest)

    def test_sha1_empty(self):
        h = Hash.sha1_new()
        digest = h.digest()
        expected = b'\xda\x39\xa3\xee\x5e\x6b\x4b\x0d\x32\x55\xbf\xef\x95\x60\x18\x90\xaf\xd8\x07\x09'
        self.assertEqual(expected, digest)

    def test_sha1_one_shot(self):
        h = Hash.sha1_new()
        h.update('abc')
        digest = h.digest()
        expected = b'\xa9\x99\x3e\x36\x47\x06\x81\x6a\xba\x3e\x25\x71\x78\x50\xc2\x6c\x9c\xd0\xd8\x9d'
        self.assertEqual(expected, digest)

    def test_sha1_iterated(self):
        h = Hash.sha1_new()
        h.update('a')
        h.update('b')
        h.update('c')
        digest = h.digest()
        expected = b'\xa9\x99\x3e\x36\x47\x06\x81\x6a\xba\x3e\x25\x71\x78\x50\xc2\x6c\x9c\xd0\xd8\x9d'
        self.assertEqual(expected, digest)

    def test_md5_empty(self):
        h = Hash.md5_new()
        digest = h.digest()
        expected = b'\xd4\x1d\x8c\xd9\x8f\x00\xb2\x04\xe9\x80\x09\x98\xec\xf8\x42\x7e'
        self.assertEqual(expected, digest)

    def test_md5_one_shot(self):
        h = Hash.md5_new()
        h.update('abc')
        digest = h.digest()
        expected = b'\x90\x01\x50\x98\x3c\xd2\x4f\xb0\xd6\x96\x3f\x7d\x28\xe1\x7f\x72'
        self.assertEqual(expected, digest)

    def test_md5_iterated(self):
        h = Hash.md5_new()
        h.update('a')
        h.update('b')
        h.update('c')
        digest = h.digest()
        expected = b'\x90\x01\x50\x98\x3c\xd2\x4f\xb0\xd6\x96\x3f\x7d\x28\xe1\x7f\x72'
        self.assertEqual(expected, digest)


if __name__ == '__main__':
    unittest.main()
