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

import awscrt.io
import unittest


class TestEventLoopGroup(unittest.TestCase):
    def test_init_defaults(self):
        event_loop_group = awscrt.io.EventLoopGroup()

    def test_1_thread(self):
        event_loop_group = awscrt.io.EventLoopGroup(1)


class TestDefaultHostResolver(unittest.TestCase):
    def test_init(self):
        event_loop_group = awscrt.io.EventLoopGroup()
        host_resolver = awscrt.io.DefaultHostResolver(event_loop_group)


class TestClientBootstrap(unittest.TestCase):
    def test_init_defaults(self):
        event_loop_group = awscrt.io.EventLoopGroup()
        bootstrap = awscrt.io.ClientBootstrap(event_loop_group)

    def test_init(self):
        event_loop_group = awscrt.io.EventLoopGroup()
        host_resolver = awscrt.io.DefaultHostResolver(event_loop_group)
        bootstrap = awscrt.io.ClientBootstrap(event_loop_group, host_resolver)
