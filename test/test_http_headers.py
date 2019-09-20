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

from awscrt.http import HttpHeaders
import unittest


class TestHttpHeaders(unittest.TestCase):

    def test_add(self):
        h = HttpHeaders()
        h.add('Host', 'example.org')
        self.assertEqual('example.org', h.get('Host'))
        self.assertEqual(['example.org'], h.get_values('Host'))

    def test_add_multi_values(self):
        h = HttpHeaders()
        h.add('Cookie', 'a=1')
        h.add('Cookie', 'b=2')
        self.assertEqual('a=1', h.get('Cookie'))
        self.assertEqual(['a=1', 'b=2'], h.get_values('Cookie'))

    def test_add_pairs(self):
        h = HttpHeaders()
        h.add_pairs([
            ('Host', 'example.org'),
            ('Cookie', 'a=1'),
            ('Cookie', 'b=2'),
        ])
        self.assertEqual('example.org', h.get('Host'))
        self.assertEqual(['a=1', 'b=2'], h.get_values('Cookie'))

    def test_set(self):
        h = HttpHeaders()

        # create
        h.set('Host', 'example.org')
        self.assertEqual(['example.org'], h.get_values('Host'))

        # replace
        h.set('Host', 'example2.org')
        self.assertEqual(['example2.org'], h.get_values('Host'))

        # replace many
        h.add('Host', 'example3.org')
        h.add('Host', 'example4.org')
        h.set('Host', 'example5.org')
        self.assertEqual(['example5.org'], h.get_values('Host'))

    def test_get_none(self):
        h = HttpHeaders()
        self.assertIsNone(h.get('Non-Existent'))
        self.assertEqual('Banana', h.get('Non-Existent', 'Banana'))
        self.assertEqual([], h.get_values('Non-Existent'))

    def test_get_is_case_insensitive(self):
        h = HttpHeaders()
        h.set('Cookie', 'a=1')
        h.add_pairs([('cookie', 'b=2'), ('COOKIE', 'c=3')])
        h.add(u'CoOkIe', 'd=4')  # note: unicode
        self.assertEqual('a=1', h.get(u'COOKIE'))
        self.assertEqual(['a=1', 'b=2', 'c=3', 'd=4'], h.get_values('Cookie'))

    def test_iter(self):
        # test that we iterate over everything we put in
        src = [('Host', 'example.org'), ('Cookie', 'a=1')]
        h = HttpHeaders(src)
        for pair in h:
            src.remove(pair)
        self.assertEqual(0, len(src))

    def test_iter_order(self):
        # test that headers with multiple values are iterated in insertion order
        src = [('Cookie', 'a=1'), ('cookie', 'b=2')]
        h = HttpHeaders(src)
        gather = [pair for pair in h]

        # note this also compares that we preserved case of the names
        self.assertEqual(src, gather)

    def test_remove(self):
        h = HttpHeaders()

        self.assertRaises(KeyError, h.remove, 'Non-Existent')

        h.add('Host', 'example.org')
        h.remove('Host')
        self.assertIsNone(h.get('Host'))

    def test_remove_value(self):
        h = HttpHeaders()

        self.assertRaises(ValueError, h.remove_value, 'Non-Existent', 'Nope')

        # header with 1 value
        h.add('Host', 'example.org')
        self.assertRaises(ValueError, h.remove_value, 'Host', 'wrong-value')
        h.remove_value('Host', 'example.org')
        self.assertIsNone(h.get('Host'))

        # pluck out a duplicate value [1,2,2] -> [1,2]
        h.add_pairs([('Dupes', '1'), ('DUPES', '2'), ('dupes', '2')])
        h.remove_value('Dupes', '2')
        self.assertEqual(['1', '2'], h.get_values('Dupes'))

    def test_clear(self):
        h = HttpHeaders([('Host', 'example.org'), ('Cookie', 'a=1'), ('cookie', 'b=2')])
        h.clear()
        self.assertEqual([], [pair for pair in h])


if __name__ == '__main__':
    unittest.main()
