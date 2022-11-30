# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.


def from_code(code):
    """Given an AWS Common Runtime error code, return an exception.

    Returns a common Python exception type, if it's appropriate.
    For example, `code=1` aka `AWS_ERROR_OOM` will result in `MemoryError`.
    Otherwise, an :class:`AwsCrtError` is returned.

    Args:
        code (int): error code.

    Returns:
        BaseException:
    """
    builtin = _awscrt.get_corresponding_builtin_exception(code)
    if builtin:
        return builtin()

    return AwsCrtError(code=code)


class AwsCrtError(RuntimeError):
    """
    Base exception class for AWS Common Runtime exceptions.

    Args:
        code (int): Int value of error.
        name (str): Name of error (optional).
        message (str): Message about error (optional).

    Attributes:
        code (int): Int value of error.
        name (str): Name of error.
        message (str): Message about error.
    """

    def __init__(self, code, name=None, message=None):
        self.code = code
        self.name = _awscrt.get_error_name(code) if name is None else name
        self.message = _awscrt.get_error_message(code) if message is None else message

    def __repr__(self):
        return "{0}(name={1}, message={2}, code={3})".format(
            self.__class__.__name__, repr(self.name), repr(self.message), self.code)

    def __str__(self):
        return "{}: {}".format(self.name, self.message)


# putting this import at end of file to work around circular dependency
from awscrt._c_lib_importer import _awscrt  # noqa
