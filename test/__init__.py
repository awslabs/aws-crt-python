# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

# Enable native memory tracing so that tests can detect leaks.
# This env-var MUST be set before awscrt is imported.
# the "noqa" comment prevents the autoformatter from moving this line below other imports
import os
os.environ['AWS_CRT_MEMORY_TRACING'] = '2'  # noqa
os.environ['AWS_CRT_CRASH_HANDLER'] = '1'   # noqa

from awscrt import NativeResource
from awscrt._test import check_for_leaks
from awscrt.io import init_logging, LogLevel
import unittest
import sys

TIMEOUT = 30.0


class NativeResourceTest(unittest.TestCase):
    """
    Test fixture asserts there are no living NativeResources when a test completes.
    """

    _previous_test_failed = False

    def setUp(self):
        NativeResource._track_lifetime = True
        # init_logging(LogLevel.Trace, 'stderr')

    def tearDown(self):
        # Stop checking for leaks if any test has failed.
        # It's likely that the failed test leaks data, which will make
        # all future tests look like they're leaking too.
        if NativeResourceTest._previous_test_failed:
            return

        # Determine whether the current test just failed.
        # This isn't possible with the public API,
        # and the technique to pull it off can vary by Python version.
        if hasattr(self._outcome, 'errors'):
            # Works in Python 3.10 and earlier
            result = self.defaultTestResult()
            self._feedErrorsToResult(result, self._outcome.errors)
        else:
            # Works in Python 3.11 and later
            result = self._outcome.result

        current_test_failed = any(failed_test == self for failed_test, _ in result.errors + result.failures)
        if current_test_failed:
            NativeResourceTest._previous_test_failed = True
            return

        # All tests have passed so far, check for leaks
        try:
            check_for_leaks(timeout_sec=TIMEOUT)
        except Exception:
            NativeResourceTest._previous_test_failed = True
            raise
