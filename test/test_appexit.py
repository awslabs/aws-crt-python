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

import subprocess
import sys
import unittest


class TestAppExit(unittest.TestCase):
    """Test that the application can exit with at any moment without native code somehow crashing python"""

    def _run_to_stage(self, module_name, stage):
        args = [sys.executable, '-m', module_name, stage.name]

        print(subprocess.list2cmdline(args))

        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)

        output = process.communicate()[0]

        # only print output if test failed
        if process.returncode != 0:
            for line in output.splitlines():
                print(line.decode())
            self.assertEqual(0, process.returncode)

    def test_http(self):
        import test.appexit_http
        for stage in test.appexit_http.Stage:
            self._run_to_stage('test.appexit_http', stage)
