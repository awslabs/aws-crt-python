# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from __future__ import absolute_import
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from test import NativeResourceTest, TIMEOUT
import unittest


class EventLoopGroupTest(NativeResourceTest):
    def test_init_defaults(self):
        event_loop_group = EventLoopGroup()

    def test_1_thread(self):
        event_loop_group = EventLoopGroup(1)

    def test_shutdown_complete(self):
        event_loop_group = EventLoopGroup()
        shutdown_event = event_loop_group.shutdown_event
        del event_loop_group
        self.assertTrue(shutdown_event.wait(TIMEOUT))


class DefaultHostResolverTest(NativeResourceTest):
    def test_init(self):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)


class ClientBootstrapTest(NativeResourceTest):
    def test_create_destroy(self):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        # ensure shutdown_event fires
        bootstrap_shutdown_event = bootstrap.shutdown_event
        del bootstrap
        self.assertTrue(bootstrap_shutdown_event.wait(TIMEOUT))


class ClientTlsContextTest(NativeResourceTest):
    def test_init_defaults(self):
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)

    def test_with_mtls_from_path(self):
        opt = TlsContextOptions.create_client_with_mtls_from_path(
            'test/resources/crt.unittests.crt', 'test/resources/crt.unittests.key')
        ctx = ClientTlsContext(opt)

    def test_with_mtls_pkcs12(self):
        opt = TlsContextOptions.create_client_with_mtls_pkcs12(
            'test/resources/crt.unittests.p12', '1234')
        ctx = ClientTlsContext(opt)

    def test_override_default_trust_store_dir(self):
        opt = TlsContextOptions()
        opt.override_default_trust_store_from_path('test/resources', None)
        ctx = ClientTlsContext(opt)

    def test_override_default_trust_store_file(self):
        opt = TlsContextOptions()
        opt.override_default_trust_store_from_path(None, 'test/resources/ca.crt')
        ctx = ClientTlsContext(opt)


class TlsConnectionOptionsTest(NativeResourceTest):
    def test_init(self):
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)
        conn_opt = TlsConnectionOptions(ctx)

    def test_alpn_list(self):
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)
        conn_opt = TlsConnectionOptions(ctx)
        conn_opt.set_alpn_list(['h2', 'http/1.1'])

    def test_server_name(self):
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)
        conn_opt = TlsConnectionOptions(ctx)
        conn_opt.set_server_name('localhost')


if __name__ == '__main__':
    unittest.main()
