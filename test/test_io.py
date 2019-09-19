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

from __future__ import absolute_import
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsContextOptions
from test import NativeResourceTest
import unittest


class EventLoopGroupTest(NativeResourceTest):
    def test_init_defaults(self):
        event_loop_group = EventLoopGroup()

    def test_1_thread(self):
        event_loop_group = EventLoopGroup(1)


class DefaultHostResolverTest(NativeResourceTest):
    def test_init(self):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)


class ClientBootstrapTest(NativeResourceTest):
    def test_init_defaults(self):
        event_loop_group = EventLoopGroup()
        bootstrap = ClientBootstrap(event_loop_group)

    def test_init(self):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)


class ClientTlsContextTest(NativeResourceTest):
    def test_init_defaults(self):
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)

    def test_with_mtls_from_path(self):
        opt = TlsContextOptions.create_client_with_mtls_from_path(
            'test/resources/unittests.crt', 'test/resources/unittests.key')
        ctx = ClientTlsContext(opt)

    def test_with_mtls_pkcs12(self):
        opt = TlsContextOptions.create_client_with_mtls_pkcs12(
            'test/resources/unittests.p12', '1234')
        ctx = ClientTlsContext(opt)

    def override_default_trust_store_dir(self):
        opt = TlsContextOptions()
        opt.override_default_trust_store_from_path('test/resources', None)
        ctx = ClientTlsContext(opt)

    def override_default_trust_store_file(self):
        opt = TlsContextOptions()
        opt.override_default_trust_store_from_path(None, 'test/resources/unittests.crt')
        ctx = ClientTlsContext(opt)


if __name__ == '__main__':
    unittest.main()
