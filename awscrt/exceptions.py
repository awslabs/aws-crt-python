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

import _awscrt


def from_code(code):
    """Given an AWS Common Runtime error-code, return an exception"""
    builtin = _awscrt.get_corresponding_builtin_exception(code)
    if builtin:
        return builtin()

    name = _awscrt.get_error_name(code)
    msg = _awscrt.get_error_message(code)
    return AwsCrtError(code=code, name=name, message=msg)


class AwsCrtError(Exception):
    """
    Base exception class for AWS Common Runtime exceptions.

    Attributes:
        code (int): Int value of error.
        name (str): Name of error.
        message (str): Message about error.
    """

    def __init__(self, code, name, message):
        self.code = code
        self.name = name
        self.message = message

    def __repr__(self):
        return "{}(code={}, name={}, message={})".format(
            self.__class__.__name__, self.code, repr(self.name), repr(self.message))
