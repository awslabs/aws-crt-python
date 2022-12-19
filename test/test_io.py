# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.io import *
from test import NativeResourceTest, TIMEOUT
import io
import os
import sys
import unittest


class EventLoopGroupTest(NativeResourceTest):
    def test_init_defaults(self):
        event_loop_group = EventLoopGroup()

    def test_1_thread(self):
        event_loop_group = EventLoopGroup(1)

    def test_cpu_group(self):
        event_loop_group = EventLoopGroup(cpu_group=0)

    def test_shutdown_complete(self):
        event_loop_group = EventLoopGroup()
        shutdown_event = event_loop_group.shutdown_event
        del event_loop_group
        self.assertTrue(shutdown_event.wait(TIMEOUT))

    def test_init_defaults_singleton(self):
        event_loop_group = EventLoopGroup.get_or_create_static_default()

    def test_init_defaults_singleton_is_singleton(self):
        event_loop_group_one = EventLoopGroup.get_or_create_static_default()
        event_loop_group_two = EventLoopGroup.get_or_create_static_default()
        self.assertTrue(event_loop_group_one == event_loop_group_two)

    def test_shutdown_complete_singleton(self):
        event_loop_group = EventLoopGroup.get_or_create_static_default()
        shutdown_event = event_loop_group.shutdown_event
        del event_loop_group
        EventLoopGroup.release_static_default()
        self.assertTrue(shutdown_event.wait(TIMEOUT))


class DefaultHostResolverTest(NativeResourceTest):
    def test_init(self):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)

    def test_init_singleton(self):
        host_resolver = DefaultHostResolver.get_or_create_static_default()

    def test_init_singleton_is_singleton(self):
        host_resolver_one = DefaultHostResolver.get_or_create_static_default()
        host_resolver_two = DefaultHostResolver.get_or_create_static_default()
        self.assertTrue(host_resolver_one == host_resolver_two)


class ClientBootstrapTest(NativeResourceTest):
    def test_create_destroy(self):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        # ensure shutdown_event fires
        bootstrap_shutdown_event = bootstrap.shutdown_event
        del bootstrap
        self.assertTrue(bootstrap_shutdown_event.wait(TIMEOUT))

    def test_create_destroy_singleton(self):
        bootstrap = ClientBootstrap.get_or_create_static_default()

        # ensure shutdown_event fires
        bootstrap_shutdown_event = bootstrap.shutdown_event
        del bootstrap
        ClientBootstrap.release_static_default()
        self.assertTrue(bootstrap_shutdown_event.wait(TIMEOUT))

    def test_init_singleton_is_singleton(self):
        client_one = ClientBootstrap.get_or_create_static_default()
        client_two = ClientBootstrap.get_or_create_static_default()
        self.assertTrue(client_one == client_two)


class ClientTlsContextTest(NativeResourceTest):
    def test_init_defaults(self):
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)

    def test_with_mtls_from_path(self):
        opt = TlsContextOptions.create_client_with_mtls_from_path(
            'test/resources/unittest.crt', 'test/resources/unittest.key')
        ctx = ClientTlsContext(opt)

    def test_with_mtls_pkcs12(self):
        try:
            opt = TlsContextOptions.create_client_with_mtls_pkcs12(
                'test/resources/unittest.p12', '1234')
            ctx = ClientTlsContext(opt)
        except Exception as e:
            if 'PLATFORM_NOT_SUPPORTED' in str(e):
                raise unittest.SkipTest(f'PKCS#12 not supported on this platform ({sys.platform})')
            else:
                # well then this is a real error
                raise e

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


class MockPythonStream:
    """For testing duck-typed stream classes.
    Doesn't inherit from io.IOBase. Doesn't implement readinto()"""

    def __init__(self, src_data):
        self.data = bytes(src_data)
        self.len = len(src_data)
        self.pos = 0

    def seek(self, where):
        self.pos = where

    def tell(self):
        return self.pos

    def read(self, amount=None):
        if amount is None:
            amount = self.len - self.pos
        else:
            amount = min(amount, self.len - self.pos)
        prev_pos = self.pos
        self.pos += amount
        return self.data[prev_pos: self.pos]


class InputStreamTest(NativeResourceTest):
    def _test(self, python_stream, expected):
        input_stream = InputStream(python_stream)
        result = bytearray()
        fixed_mv_len = 4
        fixed_mv = memoryview(bytearray(fixed_mv_len))
        while True:
            read_len = input_stream._read_into_memoryview(fixed_mv)
            if read_len is None:
                continue
            if read_len == 0:
                break
            if read_len > 0:
                self.assertLessEqual(read_len, fixed_mv_len)
                result += fixed_mv[0:read_len]

        self.assertEqual(expected, result)

    def test_read_official_io(self):
        # Read from a class defined in the io module
        src_data = b'a long string here'
        python_stream = io.BytesIO(src_data)
        self._test(python_stream, src_data)

    def test_read_duck_typed_io(self):
        # Read from a class defined in the io module
        src_data = b'a man a can a planal canada'
        python_stream = MockPythonStream(src_data)
        self._test(python_stream, src_data)


class Pkcs11LibTest(NativeResourceTest):
    def _lib_path(self):
        name = 'AWS_TEST_PKCS11_LIB'
        val = os.environ.get(name)
        if not val:
            raise unittest.SkipTest(f"test requires env var: {name}")
        return val

    def test_init(self):
        # sanity check that we can create/destroy
        lib_path = self._lib_path()
        pcks11_lib = Pkcs11Lib(file=lib_path, behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)

    def test_exceptions(self):
        # check that initialization errors bubble up as exceptions
        with self.assertRaises(Exception):
            pkcs11_lib = Pkcs11Lib(file='obviously-invalid-path.so')

        with self.assertRaises(Exception):
            with open(self._lib_path()) as literal_open_file:
                # a filepath str should passed, not a literal open file
                pkcs11_lib = Pkcs11Lib(file=literal_open_file)

    def test_strict_behavior(self):
        lib_path = self._lib_path()
        lib1 = Pkcs11Lib(file=lib_path, behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)
        # InitializeFinalizeBehavior.STRICT behavior should fail if the PKCS#11 lib is already loaded
        with self.assertRaises(Exception):
            lib2 = Pkcs11Lib(file=lib_path, behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)

    def test_omit_behavior(self):
        lib_path = self._lib_path()
        # InitializeFinalizeBehavior.OMIT should fail unless another instance of the PKCS#11 lib is already loaded
        with self.assertRaises(Exception):
            lib = Pkcs11Lib(file=lib_path, behavior=Pkcs11Lib.InitializeFinalizeBehavior.OMIT)

        # InitializeFinalizeBehavior.OMIT behavior should be fine when another
        # instance of the PKCS#11 lib is already loaded
        strict_lib = Pkcs11Lib(file=lib_path, behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)
        omit_lib = Pkcs11Lib(file=lib_path, behavior=Pkcs11Lib.InitializeFinalizeBehavior.OMIT)

    def test_is_tls_cipher_supported(self):
        self.assertEqual(True, TlsCipherPref.DEFAULT.is_supported())


if __name__ == '__main__':
    unittest.main()
