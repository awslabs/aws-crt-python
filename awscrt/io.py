# Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import _awscrt
from awscrt import CrtResource
from enum import IntEnum


class LogLevel(IntEnum):
    NoLogs = 0
    Fatal = 1
    Error = 2
    Warn = 3
    Info = 4
    Debug = 5
    Trace = 6

def init_logging(log_level, file_name):
    """
    initialize a logger. log_level is type LogLevel, and file_name is of type str.
    To write to stdout, or stderr, simply pass 'stdout' or 'stderr' as strings. Otherwise, a file path is assumed.
    """
    assert log_level is not None
    assert file_name is not None

    _awscrt.init_logging(log_level, file_name)


def is_alpn_available():
    return _awscrt.is_alpn_available()


class EventLoopGroup(CrtResource):
    """
    Manages a collection of event-loops.
    An event-loop is a thread for doing async work, such as I/O.
    Classes that need to do async work will ask the EventLoopGroup for an event-loop to use.
    """

    __slots__ = ()

    def __init__(self, num_threads=0):
        """
        num_threads: Number of event-loops to create. Pass 0 to create one for each processor on the machine.
        """
        super(CrtResource, self).__init__()
        self._binding = _awscrt.event_loop_group_new(num_threads)

class HostResolver(CrtResource):
    __slots__ = ()

class DefaultHostResolver(HostResolver):
    __slots__ = ()

    def __init__(self, event_loop_group, max_hosts=16):
        assert isinstance(event_loop_group, EventLoopGroup)

        super(DefaultHostResolver, self).__init__()
        self._binding = _awscrt.host_resolver_new_default(max_hosts, event_loop_group)

class ClientBootstrap(CrtResource):
    __slots__ = ()

    def __init__(self, event_loop_group, host_resolver=None):
        assert isinstance(event_loop_group, EventLoopGroup)
        assert isinstance(host_resolver, HostResolver) or host_resolver is None

        super(CrtResource, self).__init__()

        if host_resolver is None:
            host_resolver = DefaultHostResolver(event_loop_group)

        self._binding = _awscrt.client_bootstrap_new(event_loop_group, host_resolver)

def byte_buf_from_file(filepath):
    with open(filepath, mode='rb') as fh:
        contents = fh.read()
    return contents


class SocketDomain(IntEnum):
    IPv4 = 0
    IPv6 = 1
    Local = 2


class SocketType(IntEnum):
    Stream = 0
    DGram = 1


class SocketOptions(object):
    __slots__ = (
        'domain', 'type', 'connect_timeout_ms', 'keep_alive',
        'keep_alive_timeout_secs', 'keep_alive_interval_secs', 'keep_alive_max_probes'
    )

    def __init__(self):
        for slot in self.__slots__:
            setattr(self, slot, None)

        self.domain = SocketDomain.IPv6
        self.type = SocketType.Stream
        self.connect_timeout_ms = 3000
        self.keep_alive = False
        self.keep_alive_interval_secs = 0
        self.keep_alive_timeout_secs = 0
        self.keep_alive_max_probes = 0


class TlsVersion(IntEnum):
    SSLv3 = 0
    TLSv1 = 1
    TLSv1_1 = 2
    TLSv1_2 = 3
    TLSv1_3 = 4
    DEFAULT = 128


class TlsContextOptions(object):
    __slots__ = (
        'min_tls_ver', 'ca_path', 'ca_buffer', 'alpn_list',
        'certificate_buffer', 'private_key_buffer',
        'pkcs12_path', 'pkcs12_password', 'verify_peer')

    def __init__(self):

        for slot in self.__slots__:
            setattr(self, slot, None)

        self.min_tls_ver = TlsVersion.DEFAULT
        self.verify_peer = True

    def override_default_trust_store_from_path(self, ca_path, ca_file):

        assert isinstance(ca_path, str) or ca_path is None
        assert isinstance(ca_file, str) or ca_file is None

        ca_buffer = None
        if ca_file:
            ca_buffer = byte_buf_from_file(ca_file)

        self.ca_path = ca_path
        self.override_default_trust_store(ca_buffer)

    def override_default_trust_store(self, rootca_buffer):
        assert isinstance(rootca_buffer, bytes)

        self.ca_buffer = rootca_buffer

    @staticmethod
    def create_client_with_mtls_from_path(cert_path, pk_path):

        assert isinstance(cert_path, str)
        assert isinstance(pk_path, str)

        cert_buffer = byte_buf_from_file(cert_path)
        key_buffer = byte_buf_from_file(pk_path)

        return TlsContextOptions.create_client_with_mtls(cert_buffer, key_buffer)

    @staticmethod
    def create_client_with_mtls(cert_buffer, key_buffer):
        assert isinstance(cert_buffer, bytes)
        assert isinstance(key_buffer, bytes)

        opt = TlsContextOptions()
        opt.certificate_buffer = cert_buffer
        opt.private_key_buffer = key_buffer

        opt.verify_peer = True
        return opt

    @staticmethod
    def create_client_with_mtls_pkcs12(pkcs12_path, pkcs12_password):

        assert isinstance(pkcs12_path, str)
        assert isinstance(pkcs12_password, str)

        opt = TlsContextOptions()
        opt.pkcs12_path = pkcs12_path
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = True
        return opt

    @staticmethod
    def create_server_from_path(cert_path, pk_path):

        assert isinstance(cert_path, str)
        assert isinstance(pk_path, str)

        cert_buffer = byte_buf_from_file(cert_path)
        key_buffer = byte_buf_from_file(pk_path)

        return TlsContextOptions.create_server_with_mtls(cert_buffer, key_buffer)

    @staticmethod
    def create_server(cert_buffer, key_buffer):
        assert isinstance(cert_buffer, bytes)
        assert isinstance(key_buffer, bytes)

        opt = TlsContextOptions()
        opt.certificate_buffer = cert_buffer
        opt.private_key_buffer = key_buffer
        opt.verify_peer = False
        return opt

    @staticmethod
    def create_server_pkcs12(pkcs12_path, pkcs12_password):

        assert isinstance(pkcs12_path, str)
        assert isinstance(pkcs12_password, str)

        opt = TlsContextOptions()
        opt.pkcs12_path = pkcs12_path
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = False
        return opt


class ClientTlsContext(CrtResource):
    __slots__ = ()

    def __init__(self, options):
        assert isinstance(options, TlsContextOptions)

        super(CrtResource, self).__init__()
        self._binding = _awscrt.client_tls_ctx_new(
            options.min_tls_ver.value,
            options.ca_path,
            options.ca_buffer,
            options.alpn_list,
            options.certificate_buffer,
            options.private_key_buffer,
            options.pkcs12_path,
            options.pkcs12_password,
            options.verify_peer
        )

    def new_connection_options(self):
        return TlsConnectionOptions(self)


class TlsConnectionOptions(CrtResource):
    __slots__ = ('tls_ctx')

    def __init__(self, tls_ctx):
        assert isinstance(tls_ctx, ClientTlsContext)

        super(CrtResource, self).__init__()
        self.tls_ctx = tls_ctx
        self._binding = _awscrt.tls_connections_options_new_from_ctx(tls_ctx)

    def set_alpn_list(self, alpn_list):
        _awscrt.tls_connection_options_set_alpn_list(self, alpn_list)

    def set_server_name(self, server_name):
        _awscrt.tls_connection_options_set_server_name(self, server_name)
