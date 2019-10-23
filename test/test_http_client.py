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
from awscrt.http import HttpClientConnection, HttpClientStream, HttpHeaders, HttpRequest
from awscrt.io import TlsContextOptions, ClientTlsContext, TlsConnectionOptions
from concurrent.futures import Future
from io import open  # Python2's built-in open() doesn't return a stream
import ssl
from test import NativeResourceTest
import threading
import unittest

# Use a built-in Python HTTP server to test the awscrt's HTTP client
try:
    from http.server import HTTPServer, SimpleHTTPRequestHandler
except ImportError:
    # Simple HTTP server lives in a different places in Python3 vs Python2:
    # http.server.HTTPServer               == SocketServer.TCPServer
    # http.server.SimpleHTTPRequestHandler == SimpleHTTPServer.SimpleHTTPRequestHandler
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    import SocketServer
    HTTPServer = SocketServer.TCPServer


class Response(object):
    """Holds contents of incoming response"""

    def __init__(self):
        self.status_code = None
        self.headers = None
        self.body = bytearray()

    def on_response(self, stream, status_code, headers):
        self.status_code = status_code
        self.headers = HttpHeaders(headers)

    def on_body(self, stream, chunk):
        self.body.extend(chunk)


class TestRequestHandler(SimpleHTTPRequestHandler):
    """Request handler for test server"""

    # default was HTTP/1.0.
    # specifying HTTP/1.1 keeps connection alive after handling 1 request
    protocol_version = "HTTP/1.1"

    def do_PUT(self):
        content_length = int(self.headers['Content-Length'])
        # store put request on the server object
        incoming_body_bytes = self.rfile.read(content_length)
        self.server.put_requests[self.path] = incoming_body_bytes
        self.send_response(200, 'OK')
        self.end_headers()


class TestClient(NativeResourceTest):
    hostname = 'localhost'
    timeout = 10  # seconds

    def _start_server(self, secure):
        self.server = HTTPServer((self.hostname, 0), TestRequestHandler)
        if secure:
            self.server.socket = ssl.wrap_socket(self.server.socket,
                                                 keyfile="test/resources/unittests.key",
                                                 certfile='test/resources/unittests.crt',
                                                 server_side=True)
        self.port = self.server.server_address[1]

        # put requests are stored in this dict
        self.server.put_requests = {}

        self.server_thread = threading.Thread(target=self.server.serve_forever, name='test_server')
        self.server_thread.start()

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

    def _new_client_connection(self, secure):
        if secure:
            tls_ctx_opt = TlsContextOptions()
            tls_ctx_opt.override_default_trust_store_from_path(None, 'test/resources/unittests.crt')
            tls_ctx = ClientTlsContext(tls_ctx_opt)
            tls_conn_opt = tls_ctx.new_connection_options()
            tls_conn_opt.set_server_name(self.hostname)
        else:
            tls_conn_opt = None

        connection_future = HttpClientConnection.new(self.hostname, self.port, tls_connection_options=tls_conn_opt)
        return connection_future.result(self.timeout)

    def _test_connect(self, secure):
        self._start_server(secure)
        connection = self._new_client_connection(secure)

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

    def test_connect_http(self):
        self._test_connect(secure=False)

    def test_connect_https(self):
        self._test_connect(secure=True)

    # The connection should shut itself down cleanly when the GC collects the HttpClientConnection Python object.
    def _test_connection_closes_on_zero_refcount(self, secure):
        self._start_server(secure)

        connection = self._new_client_connection(secure)

        # Subscribing for the shutdown callback shouldn't affect the refcount of the HttpClientConnection.
        close_future = Future()

        def on_close(error_code):
            close_future.set_result(error_code)

        connection.add_shutdown_callback(on_close)

        # This should cause the GC to collect the HttpClientConnection
        del connection

        close_code = close_future.result(self.timeout)
        self.assertEqual(0, close_code)
        self._stop_server()

    def test_connection_closes_on_zero_refcount_http(self):
        self._test_connection_closes_on_zero_refcount(secure=False)

    def test_connection_closes_on_zero_refcount_https(self):
        self._test_connection_closes_on_zero_refcount(secure=True)

    # GET request receives this very file from the server. Super meta.
    def _test_get(self, secure):
        self._start_server(secure)
        connection = self._new_client_connection(secure)

        test_asset_path = 'test/test_http_client.py'

        request = HttpRequest('GET', '/' + test_asset_path)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body)

        # wait for stream to complete
        stream_completion_result = stream.completion_future.result(self.timeout)

        self.assertEqual(200, response.status_code)
        self.assertEqual(200, stream_completion_result)

        with open(test_asset_path, 'rb') as test_asset:
            test_asset_bytes = test_asset.read()
            self.assertEqual(test_asset_bytes, response.body)

        self.assertEqual(0, connection.close().result(self.timeout))

        self._stop_server()

    def test_get_http(self):
        self._test_get(secure=False)

    def test_get_https(self):
        self._test_get(secure=True)

    # PUT request sends this very file to the server.
    def _test_put(self, secure):
        self._start_server(secure)
        connection = self._new_client_connection(secure)
        test_asset_path = 'test/test_http_client.py'
        with open(test_asset_path, 'rb') as outgoing_body_stream:
            outgoing_body_bytes = outgoing_body_stream.read()
            headers = HttpHeaders([
                ('Content-Length', str(len(outgoing_body_bytes))),
            ])

            # seek back to start of stream before trying to send it
            outgoing_body_stream.seek(0)

            request = HttpRequest('PUT', '/' + test_asset_path, headers, outgoing_body_stream)
            response = Response()
            http_stream = connection.request(request, response.on_response, response.on_body)

            # wait for stream to complete
            stream_completion_result = http_stream.completion_future.result(self.timeout)

            self.assertEqual(200, response.status_code)
            self.assertEqual(200, stream_completion_result)

            # compare what we sent against what the server received
            server_received = self.server.put_requests.get('/' + test_asset_path)
            self.assertIsNotNone(server_received)
            self.assertEqual(server_received, outgoing_body_bytes)

        self.assertEqual(0, connection.close().result(self.timeout))
        self._stop_server()

    def test_put_http(self):
        self._test_put(secure=False)

    def test_put_https(self):
        self._test_put(secure=True)

    # Ensure that stream and connection classes stay alive until work is complete
    def _test_stream_lives_until_complete(self, secure):
        self._start_server(secure)
        connection = self._new_client_connection(secure)

        request = HttpRequest('GET', '/test/test_http_client.py')
        stream = connection.request(request)
        completion_future = stream.completion_future

        # delete all local references
        del stream
        del connection

        # stream should still complete successfully
        completion_future.result(self.timeout)

        self._stop_server()

    def test_stream_lives_until_complete_http(self):
        self._test_stream_lives_until_complete(secure=False)

    def test_stream_lives_until_complete_https(self):
        self._test_stream_lives_until_complete(secure=True)


if __name__ == '__main__':
    unittest.main()
