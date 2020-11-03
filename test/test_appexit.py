# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import subprocess
import sys
import unittest


class TestAppExit(unittest.TestCase):
    """Test that the application can exit with at any moment without native code somehow crashing python"""

    def _run_to_stage(self, module_name, stage):
        args = [sys.executable, '-m', module_name, stage.name]

        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)

        output = process.communicate()[0]

        # only print output if test failed
        if process.returncode != 0:
            print(subprocess.list2cmdline(args))

            for line in output.splitlines():
                print(line.decode())

            self.assertEqual(0, process.returncode)

    def test_http(self):
        import test.appexit_http
        for stage in test.appexit_http.Stage:
            self._run_to_stage('test.appexit_http', stage)
