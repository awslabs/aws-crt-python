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
from awscrt.http import HttpClientConnection
from awscrt.io import TlsContextOptions, ClientTlsContext, TlsConnectionOptions
import ssl
from test import NativeResourceTest
import threading

# Python's simple HTTP server lives in different places in Python 2/3.
try:
    from http.server import HTTPServer, SimpleHTTPRequestHandler
except ImportError:
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    import SocketServer
    HTTPServer = SocketServer.TCPServer


class TestConnection(NativeResourceTest):
    hostname = 'localhost'
    timeout = 10  # seconds

    def _start_server(self, tls=False):
        self.server = HTTPServer((self.hostname, 0), SimpleHTTPRequestHandler)
        if tls:
            self.server.socket = ssl.wrap_socket(self.server.socket,
                                                 keyfile="test/resources/unittests.key",
                                                 certfile='test/resources/unittests.crt',
                                                 server_side=True)
        self.port = self.server.server_address[1]
        self.server_thread = threading.Thread(target=self.server.serve_forever, name='test_server')
        self.server_thread.start()

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

    def _new_client_connection(self, tls=False):
        if tls:
            tls_ctx_opt = TlsContextOptions()
            tls_ctx_opt.override_default_trust_store_from_path(None, 'test/resources/unittests.crt')
            tls_ctx = ClientTlsContext(tls_ctx_opt)
            tls_conn_opt = tls_ctx.new_connection_options()
            tls_conn_opt.set_server_name(self.hostname)
        else:
            tls_conn_opt = None

        connection_future = HttpClientConnection.new(self.hostname, self.port, tls_connection_options=tls_conn_opt)
        return connection_future.result(self.timeout)

    def _test_connect(self, tls):
        self._start_server(tls)
        connection = self._new_client_connection(tls)

        # register shutdown callback
        shutdown_callback_results = []

        def shutdown_callback(error_code):
            shutdown_callback_results.append(error_code)

        connection.add_shutdown_callback(shutdown_callback)

        # close connection
        shutdown_error_code_from_close_future = connection.close().result(self.timeout)

        # assert that error code was reported via close_future and shutdown callback
        # error_code should be 0 (normal shutdown)
        self.assertEqual(0, shutdown_error_code_from_close_future)
        self.assertEqual(1, len(shutdown_callback_results))
        self.assertEqual(0, shutdown_callback_results[0])
        self.assertFalse(connection.is_open())

        self._stop_server()

    def test_connect(self):
        self._test_connect(tls=False)

    def test_connect_tls(self):
        self._test_connect(tls=True)


if __name__ == '__main__':
    unittest.main()
