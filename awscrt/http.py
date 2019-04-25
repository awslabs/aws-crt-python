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

import _aws_crt_python
from concurrent.futures import Future
from awscrt.io import ClientBootstrap, TlsConnectionOptions, SocketOptions

class HttpClientConnection(object):
    __slots__ = ('_bootstrap', '_tls_connection_options', '_on_connection_shutdown', '_native_handle')

    # don't call me, I'm private
    def __init__(self, bootstrap, on_connection_shutdown, tls_connection_options):
        assert isinstance(bootstrap, ClientBootstrap)
        self._bootstrap = bootstrap
        self._tls_connection_options = tls_connection_options
        self._on_connection_shutdown = on_connection_shutdown
        self._native_handle = None

    @staticmethod
    def new_connection(bootstrap, host_name, port, socket_options, on_connection_shutdown, tls_connection_options):
        assert tls_connection_options is None or isinstance(tls_connection_options, TlsConnectionOptions)
        assert host_name is not None
        assert port is not None
        assert socket_options is not None and isinstance(socket_options, SocketOptions)
        assert on_connection_shutdown is not None

        future = Future()
        connection = HttpClientConnection(bootstrap, on_connection_shutdown, tls_connection_options)

        def on_connection_setup_native_cb(native_handle, error_code):
            if error_code == 0:
                connection._native_handle = native_handle
                future.set_result(connection)
            else:
                future.set_exception(Exception("Error during connect: err={}".format(error_code)))

        try:
            _aws_crt_python.aws_py_http_client_connection_create(bootstrap._internal_bootstrap,
                                                                 on_connection_setup_native_cb,
                                                                 connection._on_connection_shutdown,
                                                                 host_name,
                                                                 port,
                                                                 socket_options,
                                                                 tls_connection_options._internal_tls_conn_options)

        except Exception as e:
            future.set_exception(e)

        return future

    def close(self):
        if self._native_handle is not None:
            _aws_crt_python.aws_py_http_client_connection_close(self._native_handle)

    def is_open(self):
        if self._native_handle is not None:
            return _aws_crt_python.aws_py_http_client_connection_is_open(self._native_handle)

        return False


