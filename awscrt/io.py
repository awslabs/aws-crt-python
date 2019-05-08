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

import _aws_crt_python
from enum import IntEnum


class LogLevel(IntEnum):
    NoLogs = 0
    Fatal = 1
    Error = 2
    Warn = 3
    Info = 4
    Debug = 5
    Trace = 6


class Logger(object):
    """
    initialize a logger. log_level is type LogLevel, and file_name is of type str.
    To write to stdout, or stderr, simply pass 'stdout' or 'stderr' as strings. Otherwise, a file path is assumed.
    """
    __slots__ = ('_internal_logger')

    def __init__(self, log_level, file_name):
        assert log_level is not None
        assert file_name is not None

        self._internal_logger = _aws_crt_python.aws_py_io_init_logging(log_level, file_name)


def is_alpn_available():
    return _aws_crt_python.aws_py_is_alpn_available()


class EventLoopGroup(object):
    __slots__ = ('_internal_elg')

    def __init__(self, num_threads):
        self._internal_elg = _aws_crt_python.aws_py_io_event_loop_group_new(num_threads)


class HostResolver(object):
    __slots__ = ('elg', '_internal_host_resolver')

    def __init__(self, elg):
        self.elg = elg


class DefaultHostResolver(HostResolver):
    __slots__ = ('elg', '_internal_host_resolver')

    def __init__(self, elg, max_hosts=16):
        super(DefaultHostResolver, self).__init__(elg)
        self._internal_host_resolver = _aws_crt_python.aws_py_io_host_resolver_new_default(max_hosts, elg._internal_elg)


class ClientBootstrap(object):
    __slots__ = ('elg', 'host_resolver', '_internal_bootstrap')

    def __init__(self, elg, host_resolver=None):
        assert isinstance(elg, EventLoopGroup)
        assert isinstance(host_resolver, HostResolver) or host_resolver is None

        if host_resolver is None:
            host_resolver = DefaultHostResolver(elg)

        self.elg = elg
        self.host_resolver = host_resolver
        self._internal_bootstrap = _aws_crt_python.aws_py_io_client_bootstrap_new(self.elg._internal_elg, host_resolver._internal_host_resolver)


#
def byte_buf_null_terminate(buf):
    """
    force null termination at the end of buffer
    :param buf: buffer to null terminate
    :return: null terminated buffer
    """
    if not buf.endswith(bytes([0])):
        # I know this looks hacky. please don't change it
        # because appending bytes([0]) does not work in python 2.7
        # this works in both.
        buf = buf + b'\0'
    return buf


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

        self.ca_buffer = byte_buf_null_terminate(rootca_buffer)

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
        opt.certificate_buffer = byte_buf_null_terminate(cert_buffer)
        opt.private_key_buffer = byte_buf_null_terminate(key_buffer)

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
    def create_server_with_mtls_from_path(cert_path, pk_path):

        assert isinstance(cert_path, str)
        assert isinstance(pk_path, str)

        cert_buffer = byte_buf_from_file(cert_path)
        key_buffer = byte_buf_from_file(pk_path)
        
        return TlsContextOptions.create_server_with_mtls(cert_buffer, key_buffer)

    @staticmethod
    def create_server_with_mtls(cert_buffer, key_buffer):
        assert isinstance(cert_buffer, bytes)
        assert isinstance(key_buffer, bytes)

        opt = TlsContextOptions()
        opt.certificate_buffer = byte_buf_null_terminate(cert_buffer)
        opt.private_key_buffer = byte_buf_null_terminate(key_buffer)
        opt.verify_peer = False
        return opt

    @staticmethod
    def create_server_with_mtls_pkcs12(pkcs12_path, pkcs12_password):

        assert isinstance(pkcs12_path, str)
        assert isinstance(pkcs12_password, str)

        opt = TlsContextOptions()
        opt.pkcs12_path = pkcs12_path
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = False
        return opt


class ClientTlsContext(object):

    def __init__(self, options):
        assert isinstance(options, TlsContextOptions)

        self._internal_tls_ctx = _aws_crt_python.aws_py_io_client_tls_ctx_new(
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


class TlsConnectionOptions(object):
    __slots__ = ('tls_ctx', '_internal_tls_conn_options')

    def __init__(self, tls_ctx):
        assert isinstance(tls_ctx, ClientTlsContext)

        self.tls_ctx = tls_ctx
        self._internal_tls_conn_options = _aws_crt_python.aws_py_io_tls_connections_options_new_from_ctx(tls_ctx._internal_tls_ctx)

    def set_alpn_list(self, alpn_list):
        _aws_crt_python.aws_py_io_tls_connection_options_set_alpn_list(self._internal_tls_conn_options, alpn_list)

    def set_server_name(self, server_name):
        _aws_crt_python.aws_py_io_tls_connection_options_set_server_name(self._internal_tls_conn_options, server_name)


