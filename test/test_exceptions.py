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
