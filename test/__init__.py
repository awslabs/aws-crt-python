# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt import NativeResource
from awscrt._test import check_for_leaks
from awscrt.io import init_logging, LogLevel
import unittest
import sys

TIMEOUT = 10.0


class NativeResourceTest(unittest.TestCase):
    """
    Test fixture asserts there are no living NativeResources when a test completes.
    """

    _previous_test_failed = False

    def setUp(self):
        NativeResource._track_lifetime = True
        #init_logging(LogLevel.Trace, 'stderr')

    def tearDown(self):
        # Stop checking for leaks if any test has failed.
        # It's likely that the failed test leaks data, which will make
        # all future tests look like they're leaking too.
        if NativeResourceTest._previous_test_failed:
            return

        # Determine whether the current test just failed.
        # We check private members in unittest.TestCase to do this,
        # so the technique may stop working in some future python version.
        for outcome_err in self._outcome.errors:
            if outcome_err[1] is not None:
                NativeResourceTest._previous_test_failed = True
                return

        try:
            check_for_leaks(timeout_sec=TIMEOUT)
        except Exception:
            NativeResourceTest._previous_test_failed = True
            raise
