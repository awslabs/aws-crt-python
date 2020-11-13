# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.eventstream import *
from test import NativeResourceTest
import time
from uuid import UUID, uuid4


class TestHeaders(NativeResourceTest):
    def test_bool_true(self):
        name = 'truthy'
        value = True
        h = Header.from_bool(name, value)
        self.assertIs(HeaderType.BOOL_TRUE, h.type)
        self.assertEqual(value, h.value_as_bool())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_bool_false(self):
        name = 'falsey'
        value = False
        h = Header.from_bool(name, value)
        self.assertIs(HeaderType.BOOL_FALSE, h.type)
        self.assertEqual(value, h.value_as_bool())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_byte(self):
        name = 'bytey'
        value = 127
        h = Header.from_byte(name, value)
        self.assertIs(HeaderType.BYTE, h.type)
        self.assertEqual(value, h.value_as_byte())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, Header.from_byte, 'too-big', 128)
        self.assertRaises(ValueError, Header.from_byte, 'too-small', -129)

    def test_int16(self):
        name = 'sweet16'
        value = 32000
        h = Header.from_int16(name, value)
        self.assertIs(HeaderType.INT16, h.type)
        self.assertEqual(value, h.value_as_int16())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, Header.from_int16, 'too-big', 64000)
        self.assertRaises(ValueError, Header.from_int16, 'too-small', -64000)

    def test_int32(self):
        name = 'win32'
        value = 2000000000
        h = Header.from_int32(name, value)
        self.assertIs(HeaderType.INT32, h.type)
        self.assertEqual(value, h.value_as_int32())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, Header.from_int32, 'too-big', 4000000000)
        self.assertRaises(ValueError, Header.from_int32, 'too-small', -4000000000)

    def test_int64(self):
        name = 'N64'
        value = 9223372036854775807
        h = Header.from_int64(name, value)
        self.assertIs(HeaderType.INT64, h.type)
        self.assertEqual(value, h.value_as_int64())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, Header.from_int32, 'too-big', 18000000000000000000)
        self.assertRaises(ValueError, Header.from_int32, 'too-small', -18000000000000000000)

    def test_byte_buf(self):
        name = 'buffy'
        value = bytes(range(0, 256)) * 100
        h = Header.from_byte_buf(name, value)
        self.assertIs(HeaderType.BYTE_BUF, h.type)
        self.assertEqual(value, h.value_as_byte_buf())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_string(self):
        name = 'stringy'
        value = 'abcdefghijklmnopqrstuvwxyz' * 100
        h = Header.from_string(name, value)
        self.assertIs(HeaderType.STRING, h.type)
        self.assertEqual(value, h.value_as_string())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_timestamp(self):
        name = 'timeywimey'
        value = time.time()
        h = Header.from_timestamp(name, value)
        self.assertIs(HeaderType.TIMESTAMP, h.type)
        # compare with delta, since protocol uses int instead of float
        self.assertAlmostEqual(value, h.value_as_timestamp(), delta=1.0)
        self.assertAlmostEqual(value, h.value, delta=1.0)
        self.assertEqual(name, h.name)

    def test_uuid(self):
        name = 'davuuid'
        value = UUID('01234567-89ab-cdef-0123-456789abcdef')
        h = Header.from_uuid(name, value)
        self.assertIs(HeaderType.UUID, h.type)
        self.assertEqual(value, h.value_as_uuid())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_wrong_type(self):
        h = Header.from_bool('truthy', True)
        self.assertRaises(TypeError, h.value_as_byte)
        self.assertRaises(TypeError, h.value_as_int16)
        self.assertRaises(TypeError, h.value_as_int32)
        self.assertRaises(TypeError, h.value_as_int64)
        self.assertRaises(TypeError, h.value_as_byte_buf)
        self.assertRaises(TypeError, h.value_as_string)
        self.assertRaises(TypeError, h.value_as_timestamp)
        self.assertRaises(TypeError, h.value_as_uuid)

        h = Header.from_int32('32', 32)
        self.assertRaises(TypeError, h.value_as_bool)
        self.assertRaises(TypeError, h.value_as_int64)
