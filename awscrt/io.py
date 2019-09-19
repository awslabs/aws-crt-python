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
from awscrt import NativeResource, isinstance_str
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


class EventLoopGroup(NativeResource):
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
        super(EventLoopGroup, self).__init__()
        self._binding = _awscrt.event_loop_group_new(num_threads)

class HostResolverBase(NativeResource):
    __slots__ = ()

class DefaultHostResolver(HostResolverBase):
    __slots__ = ()

    def __init__(self, event_loop_group, max_hosts=16):
        assert isinstance(event_loop_group, EventLoopGroup)

        super(DefaultHostResolver, self).__init__()
        self._binding = _awscrt.host_resolver_new_default(max_hosts, event_loop_group)

class ClientBootstrap(NativeResource):
    __slots__ = ()

    def __init__(self, event_loop_group, host_resolver=None):
        assert isinstance(event_loop_group, EventLoopGroup)
        assert isinstance(host_resolver, HostResolverBase) or host_resolver is None

        super(ClientBootstrap, self).__init__()

        if host_resolver is None:
            host_resolver = DefaultHostResolver(event_loop_group)

        self._binding = _awscrt.client_bootstrap_new(event_loop_group, host_resolver)

def _read_binary_file(filepath):
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
        'min_tls_ver', 'ca_dirpath', 'ca_buffer', 'alpn_list',
        'certificate_buffer', 'private_key_buffer',
        'pkcs12_filepath', 'pkcs12_password', 'verify_peer')

    def __init__(self):

        for slot in self.__slots__:
            setattr(self, slot, None)

        self.min_tls_ver = TlsVersion.DEFAULT
        self.verify_peer = True

    def override_default_trust_store_from_path(self, ca_dirpath, ca_filepath):

        assert isinstance_str(ca_dirpath) or ca_dirpath is None
        assert isinstance_str(ca_filepath) or ca_filepath is None

        if ca_filepath:
            ca_buffer = _read_binary_file(ca_filepath)
            self.override_default_trust_store(ca_buffer)

        self.ca_dirpath = ca_dirpath

    def override_default_trust_store(self, rootca_buffer):
        assert isinstance(rootca_buffer, bytes)

        self.ca_buffer = rootca_buffer

    @staticmethod
    def create_client_with_mtls_from_path(cert_filepath, pk_filepath):

        assert isinstance_str(cert_filepath)
        assert isinstance_str(pk_filepath)

        cert_buffer = _read_binary_file(cert_filepath)
        key_buffer = _read_binary_file(pk_filepath)

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
    def create_client_with_mtls_pkcs12(pkcs12_filepath, pkcs12_password):

        assert isinstance_str(pkcs12_filepath)
        assert isinstance_str(pkcs12_password)

        opt = TlsContextOptions()
        opt.pkcs12_filepath = pkcs12_filepath
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = True
        return opt

    @staticmethod
    def create_server_from_path(cert_filepath, pk_filepath):

        assert isinstance_str(cert_filepath)
        assert isinstance_str(pk_filepath)

        cert_buffer = _read_binary_file(cert_filepath)
        key_buffer = _read_binary_file(pk_filepath)

        return TlsContextOptions.create_server(cert_buffer, key_buffer)

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
    def create_server_pkcs12(pkcs12_filepath, pkcs12_password):

        assert isinstance_str(pkcs12_filepath)
        assert isinstance_str(pkcs12_password)

        opt = TlsContextOptions()
        opt.pkcs12_filepath = pkcs12_filepath
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = False
        return opt


class ClientTlsContext(NativeResource):
    __slots__ = ()

    def __init__(self, options):
        assert isinstance(options, TlsContextOptions)

        super(ClientTlsContext, self).__init__()
        self._binding = _awscrt.client_tls_ctx_new(
            options.min_tls_ver.value,
            options.ca_dirpath,
            options.ca_buffer,
            options.alpn_list,
            options.certificate_buffer,
            options.private_key_buffer,
            options.pkcs12_filepath,
            options.pkcs12_password,
            options.verify_peer
        )

    def new_connection_options(self):
        return TlsConnectionOptions(self)


class TlsConnectionOptions(NativeResource):
    __slots__ = ('tls_ctx')

    def __init__(self, tls_ctx):
        assert isinstance(tls_ctx, ClientTlsContext)

        super(TlsConnectionOptions, self).__init__()
        self.tls_ctx = tls_ctx
        self._binding = _awscrt.tls_connections_options_new_from_ctx(tls_ctx)

    def set_alpn_list(self, alpn_list):
        _awscrt.tls_connection_options_set_alpn_list(self, alpn_list)

    def set_server_name(self, server_name):
        _awscrt.tls_connection_options_set_server_name(self, server_name)
