# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from test import NativeResourceTest
from awscrt.common import *


class TestSystemInfo(NativeResourceTest):
    def test_get_cpu_group_count(self):
        self.assertGreater(get_cpu_group_count(), 0)

    def test_get_cpu_count_for_group(self):
        group_count = get_cpu_group_count()
        for group_i in range(group_count):
            self.assertGreater(get_cpu_count_for_group(group_i), 0)
