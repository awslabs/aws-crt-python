# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import time
import socket
import sys
import asyncio
import unittest
import threading
from test import NativeResourceTest
import ssl
import os
from io import BytesIO
from http.server import HTTPServer, SimpleHTTPRequestHandler
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from awscrt.http import HttpHeaders, HttpProxyOptions, HttpRequest, HttpVersion
from awscrt.http_asyncio import HttpClientConnectionAsync, Http2ClientConnectionAsync
import awscrt.exceptions


class Response:
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


class TestAsyncClient(NativeResourceTest):
    hostname = 'localhost'
    timeout = 5  # seconds

    def _start_server(self, secure, http_1_0=False):
        # HTTP/1.0 closes the connection at the end of each request
        # HTTP/1.1 will keep the connection alive
        if http_1_0:
            TestRequestHandler.protocol_version = "HTTP/1.0"
        else:
            TestRequestHandler.protocol_version = "HTTP/1.1"

        self.server = HTTPServer((self.hostname, 0), TestRequestHandler)
        if secure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile='test/resources/unittest.crt', keyfile="test/resources/unittest.key")
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]

        # put requests are stored in this dict
        self.server.put_requests = {}

        self.server_thread = threading.Thread(target=self.server.serve_forever, name='test_server')
        self.server_thread.start()

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

    async def _new_client_connection(self, secure, proxy_options=None):
        if secure:
            tls_ctx_opt = TlsContextOptions()
            tls_ctx_opt.verify_peer = False
            tls_ctx = ClientTlsContext(tls_ctx_opt)
            tls_conn_opt = tls_ctx.new_connection_options()
            tls_conn_opt.set_server_name(self.hostname)
        else:
            tls_conn_opt = None

        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        connection = await HttpClientConnectionAsync.new(
            host_name=self.hostname,
            port=self.port,
            bootstrap=bootstrap,
            tls_connection_options=tls_conn_opt,
            proxy_options=proxy_options)

        return connection

    async def _test_connect(self, secure):
        self._start_server(secure)
        try:
            connection = await self._new_client_connection(secure)

            # close connection
            await connection.close()
            self.assertFalse(connection.is_open())

        finally:
            self._stop_server()

    async def _test_get(self, secure):
        # GET request receives this very file from the server
        self._start_server(secure)
        try:
            connection = await self._new_client_connection(secure)

            test_asset_path = 'test/test_http_asyncio.py'

            request = HttpRequest('GET', '/' + test_asset_path)
            response = Response()
            stream = connection.request(request, response.on_response, response.on_body)
            stream.activate()

            # wait for stream to complete
            status_code = await stream.wait_for_completion()
            self.assertEqual(200, status_code)
            self.assertEqual(200, response.status_code)

            with open(test_asset_path, 'rb') as test_asset:
                test_asset_bytes = test_asset.read()
                self.assertEqual(test_asset_bytes, response.body)

            await connection.close()

        finally:
            self._stop_server()

    async def _test_put(self, secure):
        # PUT request sends this very file to the server
        self._start_server(secure)
        try:
            connection = await self._new_client_connection(secure)
            test_asset_path = 'test/test_http_asyncio.py'
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
                status_code = await http_stream.wait_for_completion()
                self.assertEqual(200, status_code)
                self.assertEqual(200, response.status_code)

                # compare what we sent against what the server received
                server_received = self.server.put_requests.get('/' + test_asset_path)
                self.assertIsNotNone(server_received)
                self.assertEqual(server_received, outgoing_body_bytes)

            await connection.close()

        finally:
            self._stop_server()

    def test_connect_http(self):
        asyncio.run(self._test_connect(secure=False))

    def test_connect_https(self):
        asyncio.run(self._test_connect(secure=True))

    def test_get_http(self):
        asyncio.run(self._test_get(secure=False))

    def test_get_https(self):
        asyncio.run(self._test_get(secure=True))

    def test_put_http(self):
        asyncio.run(self._test_put(secure=False))

    def test_put_https(self):
        asyncio.run(self._test_put(secure=True))


if __name__ == '__main__':
    unittest.main()
