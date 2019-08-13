# Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import argparse
import sys
import os
from io import BytesIO
from awscrt import io, http
import unittest

# an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
# you only want one of these.
event_loop_group = io.EventLoopGroup(1)

log_level = io.LogLevel.NoLogs
log_level = io.LogLevel.Error
log_output = 'stderr'
io.init_logging(log_level, log_output)
class TestStringMethods(unittest.TestCase):

    def test_server_bootstrap(self):
        server_bootstrap = io.ServerBootstrap(event_loop_group)
        self.assertIsNotNone(server_bootstrap)

if __name__ == '__main__':
    unittest.main()

# server bootstrap init

