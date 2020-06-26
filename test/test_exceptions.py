# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt.exceptions
import unittest


class AwsCrtErrorTest(unittest.TestCase):
    def test_error_code_conversion(self):
        err = awscrt.exceptions.from_code(0)
        self.assertEqual(0, err.code)
        self.assertEqual("AWS_ERROR_SUCCESS", err.name)
        self.assertTrue("success" in err.message.lower())

    def test_error_code_remaps_to_corresponding_builtins(self):
        err = awscrt.exceptions.from_code(1)
        self.assertEqual(MemoryError, type(err))

    def test_bad_error_code_wont_crash(self):
        err = awscrt.exceptions.from_code(999999999)
        self.assertEqual(999999999, err.code)
        self.assertIsNotNone(err.name)
        self.assertIsNotNone(err.message)
