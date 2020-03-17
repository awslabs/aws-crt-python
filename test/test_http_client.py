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
import awscrt.exceptions
from awscrt.http import HttpClientConnection, HttpClientStream, HttpHeaders, HttpProxyOptions, HttpRequest
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from concurrent.futures import Future
from io import open  # Python2's built-in open() doesn't return a stream
import os
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

PROXY_HOST = os.environ.get('proxyhost')
PROXY_PORT = int(os.environ.get('proxyport', '0'))


class Response(object):
    """Holds contents of incoming response"""

    def __init__(self):
        self.status_code = None
        self.headers = None
        self.body = bytearray()

    def on_response(self, http_stream, status_code, headers, **kwargs):
        self.status_code = status_code
        self.headers = HttpHeaders(headers)

    def on_body(self, http_stream, chunk, **kwargs):
        self.body.extend(chunk)


class TestRequestHandler(SimpleHTTPRequestHandler):
    """Request handler for test server"""

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

    def _start_server(self, secure, http_1_0=False):
        # HTTP/1.0 closes the connection at the end of each request
        # HTTP/1.1 will keep the connection alive
        if http_1_0:
            TestRequestHandler.protocol_version = "HTTP/1.0"
        else:
            TestRequestHandler.protocol_version = "HTTP/1.1"

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

    def _new_client_connection(self, secure, proxy_options=None):
        if secure:
            tls_ctx_opt = TlsContextOptions()
            tls_ctx_opt.override_default_trust_store_from_path(None, 'test/resources/unittests.crt')
            tls_ctx = ClientTlsContext(tls_ctx_opt)
            tls_conn_opt = tls_ctx.new_connection_options()
            tls_conn_opt.set_server_name(self.hostname)
        else:
            tls_conn_opt = None

        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        connection_future = HttpClientConnection.new(host_name=self.hostname,
                                                     port=self.port,
                                                     bootstrap=bootstrap,
                                                     tls_connection_options=tls_conn_opt,
                                                     proxy_options=proxy_options)
        return connection_future.result(self.timeout)

    def _test_connect(self, secure):
        self._start_server(secure)
        connection = self._new_client_connection(secure)

        # close connection
        shutdown_error_from_close_future = connection.close().exception(self.timeout)

        # assert that error was reported via close_future and shutdown callback
        # error should be None (normal shutdown)
        self.assertEqual(None, shutdown_error_from_close_future)
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

        # referencing the shutdown_future does not keep the connection alive
        close_future = connection.shutdown_future

        # This should cause the GC to collect the HttpClientConnection
        del connection

        close_error = close_future.exception(self.timeout)
        self.assertEqual(None, close_error)
        self._stop_server()

    def test_connection_closes_on_zero_refcount_http(self):
        self._test_connection_closes_on_zero_refcount(secure=False)

    def test_connection_closes_on_zero_refcount_https(self):
        self._test_connection_closes_on_zero_refcount(secure=True)

    # GET request receives this very file from the server. Super meta.
    def _test_get(self, secure, proxy_options=None):

        # Use HTTP/1.0 in proxy tests or server will keep connection with proxy alive
        # and refuse to shut down for 1 minute at the end of each proxy test
        http_1_0 = proxy_options is not None

        self._start_server(secure, http_1_0)
        connection = self._new_client_connection(secure, proxy_options)

        test_asset_path = 'test/test_http_client.py'

        request = HttpRequest('GET', '/' + test_asset_path)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body)
        stream.activate()

        # wait for stream to complete
        stream_completion_result = stream.completion_future.result(self.timeout)

        self.assertEqual(200, response.status_code)
        self.assertEqual(200, stream_completion_result)

        with open(test_asset_path, 'rb') as test_asset:
            test_asset_bytes = test_asset.read()
            self.assertEqual(test_asset_bytes, response.body)

        self.assertEqual(None, connection.close().exception(self.timeout))

        self._stop_server()

    def test_get_http(self):
        self._test_get(secure=False)

    def test_get_https(self):
        self._test_get(secure=True)

    def _test_shutdown_error(self, secure):
        # Use HTTP/1.0 connection to force a SOCKET_CLOSED error after request completes
        self._start_server(secure, http_1_0=True)
        connection = self._new_client_connection(secure)

        # Send request, don't care what happens
        request = HttpRequest('GET', '/')
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body)
        stream.activate()
        stream.completion_future.result(self.timeout)

        # Wait for server to hang up, which should be immediate since it's using HTTP/1.0
        shutdown_error = connection.shutdown_future.exception(self.timeout)
        self.assertIsInstance(shutdown_error, awscrt.exceptions.AwsCrtError)

        self._stop_server()

    def test_shutdown_error_http(self):
        return self._test_shutdown_error(secure=False)

    def test_shutdown_error_https(self):
        return self._test_shutdown_error(secure=True)

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
            http_stream.activate()
            # wait for stream to complete
            stream_completion_result = http_stream.completion_future.result(self.timeout)

            self.assertEqual(200, response.status_code)
            self.assertEqual(200, stream_completion_result)

            # compare what we sent against what the server received
            server_received = self.server.put_requests.get('/' + test_asset_path)
            self.assertIsNotNone(server_received)
            self.assertEqual(server_received, outgoing_body_bytes)

        self.assertEqual(None, connection.close().result(self.timeout))
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
        stream.activate()
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

    # If a stream is never activated, it should just clean itself up
    def _test_stream_cleans_up_if_never_activated(self, secure):
        self._start_server(secure)

        connection = self._new_client_connection(secure)
        stream = connection.request(HttpRequest('GET', '/test/test_http_client.py'))
        # note we do NOT activate the stream

        # delete local references, stream should clean itself up, connection should shut itself down
        del stream
        del connection

        self._stop_server()

    def test_stream_cleans_up_if_never_activated_http(self):
        self._test_stream_cleans_up_if_never_activated(secure=False)

    def test_stream_cleans_up_if_never_activated_https(self):
        self._test_stream_cleans_up_if_never_activated(secure=True)

    @unittest.skipIf(PROXY_HOST is None, 'requires "proxyhost" and "proxyport" env vars')
    def test_proxy_http(self):
        proxy_options = HttpProxyOptions(host_name=PROXY_HOST, port=PROXY_PORT)
        self._test_get(secure=False, proxy_options=proxy_options)


if __name__ == '__main__':
    unittest.main()
