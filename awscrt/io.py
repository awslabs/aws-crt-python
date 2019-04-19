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
    __slots__ = ('elg', '_internal_bootstrap')

    def __init__(self, elg, host_resolver):
        assert isinstance(elg, EventLoopGroup)
        assert isinstance(host_resolver, HostResolver)

        self.elg = elg
        self._internal_bootstrap = _aws_crt_python.aws_py_io_client_bootstrap_new(self.elg._internal_elg, host_resolver._internal_host_resolver)

class TlsVersion(IntEnum):
    SSLv3 = 0
    TLSv1 = 1
    TLSv1_1 = 2
    TLSv1_2 = 3
    TLSv1_3 = 4
    DEFAULT = 128

# force null termination at the end of buffer
def byte_buf_null_terminate(buf):
    if not buf.endswith(bytes([0])):
        buf = buf + bytes([0])
    return buf

def byte_buf_from_file(filepath):
    with open(filepath, mode='rb') as fh:
        contents = fh.read()
    return byte_buf_null_terminate(contents)    

class TlsContextOptions(object):
    __slots__ = (
        'min_tls_ver', 'ca_path', 'ca_buffer', 'alpn_list',
        'certificate_buffer', 'private_key_buffer',
        'pkcs12_path', 'pkcs12_password', 'verify_peer')

    def __init__(self):

        for slot in self.__slots__:
            setattr(self, slot, None)

        self.min_tls_ver = TlsVersion.DEFAULT

    @classmethod
    def override_default_trust_store_from_path(self, ca_path, ca_file):

        assert isinstance(ca_path, str) or ca_path is None
        assert isinstance(ca_file, str) or ca_file is None

        ca_buffer = None
        if ca_file:
            ca_buffer = byte_buf_from_file(ca_file)
        
        self.ca_path = ca_path
        self.override_default_trust_store(ca_buffer)

    @classmethod
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
    __slots__ = ('options', '_internal_tls_ctx')

    def __init__(self, options):
        assert isinstance(options, TlsContextOptions)

        self.options = options
        self._internal_tls_ctx = _aws_crt_python.aws_py_io_client_tls_ctx_new(
            options.min_tls_ver.value,
            options.ca_path,
            options.ca_buffer,
            options.alpn_list,
            options.certificate_buffer,
            options.private_key_buffer,
            options.pkcs12_path,
            options.pkcs12_password,
            options.verify_peer,
        )

