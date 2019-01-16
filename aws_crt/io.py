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

class ClientBootstrap(object):
    __slots__ = ('elg', '_internal_bootstrap')

    def __init__(self, elg):
        assert isinstance(elg, EventLoopGroup)

        self.elg = elg
        self._internal_bootstrap = _aws_crt_python.aws_py_io_client_bootstrap_new(self.elg._internal_elg)

class TlsVersion(IntEnum):
    SSLv3 = 0
    TLSv1 = 1
    TLSv1_1 = 2
    TLSv1_2 = 3
    TLSv1_3 = 4
    DEFAULT = 128

class TlsContextOptions(object):
    __slots__ = ('min_tls_ver', 'ca_file', 'ca_path', 'alpn_list', 'certificate_path', 'private_key_path', 'pkcs12_path', 'pkcs12_password', 'verify_peer')

    def __init__(self):

        for slot in self.__slots__:
            setattr(self, slot, None)

        self.min_tls_ver = TlsVersion.DEFAULT

    def override_default_trust_store(self, ca_path, ca_file):

        assert isinstance(ca_path, str) or ca_path is None
        assert isinstance(ca_file, str) or ca_file is None

        self.ca_path = ca_path
        self.ca_file = ca_file

    @classmethod
    def create_client_with_mtls(clazz, cert_path, pk_path):

        assert isinstance(cert_path, str)
        assert isinstance(pk_path, str)

        opt = TlsContextOptions()
        opt.certificate_path = cert_path
        opt.private_key_path = pk_path
        opt.verify_peer = True
        return opt

    @classmethod
    def create_client_with_mtls_pkcs12(clazz, pkcs12_path, pkcs12_password):

        assert isinstance(pkcs12_path, str)
        assert isinstance(pkcs12_password, str)

        opt = TlsContextOptions()
        opt.pkcs12_path = pkcs12_path
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = True
        return opt

    @classmethod
    def create_server_with_mtls(clazz, cert_path, pk_path):

        assert isinstance(cert_path, str)
        assert isinstance(pk_path, str)

        opt = TlsContextOptions()
        opt.certificate_path = cert_path
        opt.private_key_path = pk_path
        opt.verify_peer = False
        return opt

    @classmethod
    def create_server_with_mtls_pkcs12(clazz, pkcs12_path, pkcs12_password):

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
            options.ca_file,
            options.ca_path,
            options.alpn_list,
            options.certificate_path,
            options.private_key_path,
            options.pkcs12_path,
            options.pkcs12_password,
            options.verify_peer,
        )

