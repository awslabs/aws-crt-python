# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import time
import socket
import sys
import asyncio
import unittest
import threading
import subprocess
import concurrent.futures
from urllib.parse import urlparse
from test import NativeResourceTest
import ssl
import os
import json
from io import BytesIO
from http.server import HTTPServer, SimpleHTTPRequestHandler
from awscrt import io
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsContextOptions, TlsCipherPref
from awscrt.http import HttpHeaders, HttpRequest, HttpVersion, Http2Setting, Http2SettingID
from awscrt.aio.http import AIOHttpClientConnection, AIOHttp2ClientConnection
import threading


class Response:
    """Holds contents of incoming response"""

    def __init__(self):
        self.status_code = None
        self.headers = None
        self.body = bytearray()

    async def collect_response(self, stream):
        """Collects complete response from a stream"""
        # Get status code and headers
        self.status_code = await stream.get_response_status_code()
        headers_list = await stream.get_response_headers()
        self.headers = HttpHeaders(headers_list)
        # Collect body chunks
        while True:
            chunk = await stream.get_next_response_chunk()
            if not chunk:
                break
            self.body.extend(chunk)
            if hasattr(stream, 'update_window'):
                stream.update_window(len(chunk))

        # Return status code for convenience
        return self.status_code


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
            context.minimum_version = ssl.TLSVersion.TLSv1_2
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
        return await AIOHttpClientConnection.new(
            host_name=self.hostname,
            port=self.port,
            bootstrap=bootstrap,
            tls_connection_options=tls_conn_opt,
            proxy_options=proxy_options)

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
            self.assertTrue(connection.is_open())

            test_asset_path = 'test/test_aiohttp_client.py'

            # Create request and get stream - stream is already activated
            request = HttpRequest('GET', '/' + test_asset_path)
            stream = connection.request(request)

            # Collect and process response
            response = Response()
            status_code = await response.collect_response(stream)

            # Verify results
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
            test_asset_path = 'test/test_aiohttp_client.py'
            with open(test_asset_path, 'rb') as outgoing_body_stream:
                outgoing_body_bytes = outgoing_body_stream.read()
                headers = HttpHeaders([
                    ('Content-Length', str(len(outgoing_body_bytes))),
                ])

                # seek back to start of stream before trying to send it
                outgoing_body_stream.seek(0)

                # Create request and get stream - stream is already activated
                request = HttpRequest('PUT', '/' + test_asset_path, headers, outgoing_body_stream)
                stream = connection.request(request)

                # Collect and process response
                response = Response()
                status_code = await response.collect_response(stream)

                # Verify results
                self.assertEqual(200, status_code)
                self.assertEqual(200, response.status_code)

                # compare what we sent against what the server received
                server_received = self.server.put_requests.get('/' + test_asset_path)
                self.assertIsNotNone(server_received)
                self.assertEqual(server_received, outgoing_body_bytes)

            await connection.close()

        finally:
            self._stop_server()

    async def _test_shutdown_error(self, secure):
        # Use HTTP/1.0 connection to force a connection close after request completes
        self._start_server(secure, http_1_0=True)
        try:
            connection = await self._new_client_connection(secure)

            # Send request
            request = HttpRequest('GET', '/')
            stream = connection.request(request)

            # Collect response
            response = Response()
            await response.collect_response(stream)

            # With HTTP/1.0, the server should close the connection
            # We'll wait a bit and verify the connection is closed
            await asyncio.sleep(0.5)  # Give time for the server to close connection
            self.assertFalse(connection.is_open())

        finally:
            self._stop_server()

    async def _test_stream_lives_until_complete(self, secure):
        # Ensure that stream and connection classes stay alive until work is complete
        self._start_server(secure)
        try:
            connection = await self._new_client_connection(secure)

            request = HttpRequest('GET', '/test/test_aiohttp_client.py')
            stream = connection.request(request)

            # Store stream but delete all local references
            response = Response()

            # Schedule task to collect response but don't await it yet
            collect_task = asyncio.create_task(response.collect_response(stream))

            # Delete references to stream and connection
            del stream
            del connection

            # Now await the collection task - stream should still complete successfully
            status_code = await collect_task
            self.assertEqual(200, status_code)

        finally:
            self._stop_server()

    async def _test_request_lives_until_stream_complete(self, secure):
        # Ensure HttpRequest and body InputStream stay alive until HttpClientStream completes
        self._start_server(secure)
        try:
            connection = await self._new_client_connection(secure)

            request = HttpRequest(
                method='PUT',
                path='/test/test_request_refcounts.txt',
                headers=HttpHeaders([('Host', self.hostname), ('Content-Length', '5')]),
                body_stream=BytesIO(b'hello'))

            # Create stream but delete the request
            stream = connection.request(request)
            del request

            # Now collect the response - should still work since the stream keeps the request alive
            response = Response()
            status_code = await response.collect_response(stream)
            self.assertEqual(200, status_code)

            await connection.close()

        finally:
            self._stop_server()

    async def _new_h2_client_connection(self, url):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        port = url.port
        if port is None:
            port = 443

        tls_ctx_options = TlsContextOptions()
        tls_ctx_options.verify_peer = False  # Allow localhost
        tls_ctx = ClientTlsContext(tls_ctx_options)
        tls_conn_opt = tls_ctx.new_connection_options()
        tls_conn_opt.set_server_name(url.hostname)
        tls_conn_opt.set_alpn_list(["h2"])

        connection = await AIOHttp2ClientConnection.new(
            host_name=url.hostname,
            port=port,
            bootstrap=bootstrap,
            tls_connection_options=tls_conn_opt)

        return connection

    async def _test_h2_client(self):
        url = urlparse("https://d1cz66xoahf9cl.cloudfront.net/http_test_doc.txt")
        connection = await self._new_h2_client_connection(url)

        # Check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('GET', url.path)
        request.headers.add('host', url.hostname)
        stream = connection.request(request)

        response = Response()
        status_code = await response.collect_response(stream)

        # Check result
        self.assertEqual(200, status_code)
        self.assertEqual(200, response.status_code)
        self.assertEqual(14428801, len(response.body))

        await connection.close()

    async def _test_h2_manual_write_exception(self):
        url = urlparse("https://d1cz66xoahf9cl.cloudfront.net/http_test_doc.txt")
        connection = await self._new_h2_client_connection(url)

        # Check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('GET', url.path)
        request.headers.add('host', url.hostname)

        # Create stream without using request_body_generator parameter
        # (which would be needed to properly configure it for writing)
        stream = connection.request(request)

        # The stream should have write_data attribute but using it should raise an exception
        # since the stream isn't properly configured for manual writing
        exception = None
        try:
            # Attempt to access internal write_data method which should raise an exception
            # since the stream wasn't created with request_body_generator
            await stream._write_data(BytesIO(b'hello'), False)
        except (RuntimeError, AttributeError) as e:
            exception = e

        self.assertIsNotNone(exception)
        await connection.close()

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

    def test_shutdown_error_http(self):
        asyncio.run(self._test_shutdown_error(secure=False))

    def test_shutdown_error_https(self):
        asyncio.run(self._test_shutdown_error(secure=True))

    def test_stream_lives_until_complete_http(self):
        asyncio.run(self._test_stream_lives_until_complete(secure=False))

    def test_stream_lives_until_complete_https(self):
        asyncio.run(self._test_stream_lives_until_complete(secure=True))

    def test_request_lives_until_stream_complete_http(self):
        asyncio.run(self._test_request_lives_until_stream_complete(secure=False))

    def test_request_lives_until_stream_complete_https(self):
        asyncio.run(self._test_request_lives_until_stream_complete(secure=True))

    def test_h2_client(self):
        asyncio.run(self._test_h2_client())

    def test_h2_manual_write_exception(self):
        asyncio.run(self._test_h2_manual_write_exception())

    @unittest.skipIf(not TlsCipherPref.PQ_DEFAULT.is_supported(), "Cipher pref not supported")
    def test_connect_pq_default(self):
        async def _test():
            await self._test_connect(secure=True)
        asyncio.run(_test())

    async def _test_cross_thread_http_client(self, secure):
        """Test using an HTTP client from a different thread/event loop."""
        self._start_server(secure)
        try:
            # Create connection in the main thread
            connection = await self._new_client_connection(secure)
            self.assertTrue(connection.is_open())

            # Function to run in a different thread with a different event loop
            async def thread_func(conn):
                # Create new event loop for this thread
                test_asset_path = 'test/test_aiohttp_client.py'
                request = HttpRequest('GET', '/' + test_asset_path)

                # Use the connection but with the current thread's event loop
                thread_loop = asyncio.get_event_loop()
                stream = conn.request(request, loop=thread_loop)

                # Collect and process response
                response = Response()
                status_code = await response.collect_response(stream)

                # Verify results
                assert status_code == 200

                with open(test_asset_path, 'rb') as test_asset:
                    test_asset_bytes = test_asset.read()
                    assert test_asset_bytes == response.body

                return True

            # Run in executor to get a different thread
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(thread_func(connection))
                )
                result = future.result()
                self.assertTrue(result)

            await connection.close()

        finally:
            self._stop_server()

    async def _test_cross_thread_http2_client(self):
        """Test using an HTTP/2 client from a different thread/event loop."""
        url = urlparse("https://d1cz66xoahf9cl.cloudfront.net/http_test_doc.txt")
        connection = await self._new_h2_client_connection(url)

        # Check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        # Function to run in a different thread with a different event loop
        async def thread_func(conn):
            request = HttpRequest('GET', url.path)
            request.headers.add('host', url.hostname)

            # Use the connection but with the current thread's event loop
            thread_loop = asyncio.get_event_loop()
            stream = conn.request(request, loop=thread_loop)

            response = Response()
            status_code = await response.collect_response(stream)
            # Check result
            assert status_code == 200
            return len(response.body)

        # Run in executor to get a different thread
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(thread_func(connection))
            )
            body_length = future.result()
            self.assertEqual(14428801, body_length)

        await connection.close()

    def test_cross_thread_http_client(self):
        asyncio.run(self._test_cross_thread_http_client(secure=False))

    def test_cross_thread_https_client(self):
        asyncio.run(self._test_cross_thread_http_client(secure=True))

    def test_cross_thread_http2_client(self):
        asyncio.run(self._test_cross_thread_http2_client())


@unittest.skipUnless(os.environ.get('AWS_TEST_LOCALHOST'), 'set env var to run test: AWS_TEST_LOCALHOST')
class TestAsyncClientMockServer(NativeResourceTest):
    timeout = 5  # seconds
    p_server = None
    mock_server_url = None

    def setUp(self):
        super().setUp()
        # Start the mock server from the aws-c-http
        server_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'crt',
            'aws-c-http',
            'tests',
            'mock_server',
            'h2tls_mock_server.py')
        python_path = sys.executable
        self.mock_server_url = urlparse("https://localhost:3443/echo")
        self.p_server = subprocess.Popen([python_path, server_path])
        # Wait for server to be ready
        self._wait_for_server_ready()

    def _wait_for_server_ready(self):
        """Wait until server is accepting connections."""
        max_attempts = 20

        for attempt in range(max_attempts):
            try:
                with socket.create_connection(("127.0.0.1", self.mock_server_url.port), timeout=1):
                    return  # Server is ready
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.5)

        # If we get here, server failed to start
        stdout, stderr = self.p_server.communicate(timeout=0.5)
        raise RuntimeError(f"Server failed to start after {max_attempts} attempts.\n"
                           f"STDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}")

    def tearDown(self):
        self.p_server.terminate()
        try:
            self.p_server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.p_server.kill()
        super().tearDown()

    def _on_remote_settings_changed(self, settings):
        # The mock server has the default settings with
        # ENABLE_PUSH = 0
        # MAX_CONCURRENT_STREAMS = 100
        # MAX_HEADER_LIST_SIZE = 2**16
        # Check the settings here
        self.assertEqual(len(settings), 3)
        for i in settings:
            if i.id == Http2SettingID.ENABLE_PUSH:
                self.assertEqual(i.value, 0)
            if i.id == Http2SettingID.MAX_CONCURRENT_STREAMS:
                self.assertEqual(i.value, 100)
            if i.id == Http2SettingID.MAX_HEADER_LIST_SIZE:
                self.assertEqual(i.value, 2**16)

    async def _new_mock_connection(self, initial_settings=None):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        port = self.mock_server_url.port
        # only test https
        if port is None:
            port = 443
        tls_ctx_options = TlsContextOptions()
        tls_ctx_options.verify_peer = False  # allow localhost
        tls_ctx = ClientTlsContext(tls_ctx_options)
        tls_conn_opt = tls_ctx.new_connection_options()
        tls_conn_opt.set_server_name(self.mock_server_url.hostname)
        tls_conn_opt.set_alpn_list(["h2"])

        if initial_settings is None:
            initial_settings = [Http2Setting(Http2SettingID.ENABLE_PUSH, 0)]

        connection = await AIOHttp2ClientConnection.new(
            host_name=self.mock_server_url.hostname,
            port=port,
            bootstrap=bootstrap,
            tls_connection_options=tls_conn_opt,
            initial_settings=initial_settings,
            on_remote_settings_changed=self._on_remote_settings_changed)

        return connection

    async def _test_h2_mock_server_manual_write(self):
        connection = await self._new_mock_connection()
        # check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('POST', self.mock_server_url.path)
        request.headers.add('host', self.mock_server_url.hostname)

        # Create an async generator for the request body
        body_chunks = [b'hello', b'he123123', b'', b'hello']
        total_length = 0
        content = b''
        for i in body_chunks:
            total_length = total_length + len(i)
            content += i

        async def body_generator():
            for i in body_chunks:
                yield i

        stream = connection.request(request, request_body_generator=body_generator())

        # Collect response
        response = Response()
        status_code = await response.collect_response(stream)

        # Check result
        self.assertEqual(200, status_code)
        self.assertEqual(200, response.status_code)
        # Parse the response from mock server which has format:
        # {
        #   "body": <str of data received>,
        #   "bytes": <byte count of data received>
        # }
        parsed_response = json.loads(response.body.decode())
        self.assertEqual(total_length, int(parsed_response["bytes"]))
        self.assertEqual(content.decode(), parsed_response["body"])
        await connection.close()

    class DelayStream:
        def __init__(self, bad_read=False):
            self._read = False
            self.bad_read = bad_read

        def read(self, _len):
            if self.bad_read:
                # simulate a bad read that raises an exception
                # this will cause the stream to fail
                raise RuntimeError("bad read exception")
            if self._read:
                # return empty as EOS
                return b''
            else:
                self._read = True
                return b'hello'

    async def _test_h2_mock_server_settings(self):
        # Test with invalid settings - should throw an exception
        exception = None
        try:
            # Invalid settings type
            initial_settings = [100]
            await self._new_mock_connection(initial_settings)
        except Exception as e:
            exception = e
        self.assertIsNotNone(exception)

        # Test with valid settings
        connection = await self._new_mock_connection()
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('POST', self.mock_server_url.path)
        request.headers.add('host', self.mock_server_url.hostname)

        # Create an async generator for the request body
        async def body_generator():
            yield b'hello'

        stream = connection.request(request, request_body_generator=body_generator())

        response = Response()
        status_code = await response.collect_response(stream)

        self.assertEqual(200, status_code)
        self.assertEqual(200, response.status_code)

        await connection.close()

    def test_h2_mock_server_manual_write(self):
        asyncio.run(self._test_h2_mock_server_manual_write())

    def test_h2_mock_server_settings(self):
        asyncio.run(self._test_h2_mock_server_settings())


class AIOFlowControlTest(NativeResourceTest):
    timeout = 10.0

    async def _test_http1_manual_window_management_parameters(self):
        """Test HTTP/1.1 connection accepts flow control parameters"""
        tls_ctx_opt = TlsContextOptions()
        tls_ctx_opt.verify_peer = False
        tls_ctx_opt.alpn_list = ['http/1.1']
        tls_ctx = ClientTlsContext(tls_ctx_opt)
        tls_options = tls_ctx.new_connection_options()
        tls_options.set_server_name("httpbin.org")

        connection = await AIOHttpClientConnection.new(
            host_name="httpbin.org",
            port=443,
            tls_connection_options=tls_options,
            manual_window_management=True,
            initial_window_size=32768,
            read_buffer_capacity=16384
        )
        await connection.close()

    def test_http1_manual_window_management_parameters(self):
        asyncio.run(self._test_http1_manual_window_management_parameters())

    async def _test_http2_manual_window_management_parameters(self):
        """Test HTTP/2 connection accepts flow control parameters"""
        tls_ctx_opt = TlsContextOptions()
        tls_ctx_opt.verify_peer = False
        tls_ctx_opt.alpn_list = ['h2']
        tls_ctx = ClientTlsContext(tls_ctx_opt)
        tls_options = tls_ctx.new_connection_options()
        tls_options.set_server_name("httpbin.org")

        connection = await AIOHttp2ClientConnection.new(
            host_name="httpbin.org",
            port=443,
            tls_connection_options=tls_options,
            manual_window_management=True,
            initial_window_size=65536,
            conn_manual_window_management=True,
            conn_window_size_threshold=32767,
            stream_window_size_threshold=16384
        )
        await connection.close()

    def test_http2_manual_window_management_parameters(self):
        asyncio.run(self._test_http2_manual_window_management_parameters())

    async def _test_h2_connection_has_update_window_method(self):
        """Test HTTP/2 connection has update_window method"""
        tls_ctx_opt = TlsContextOptions()
        tls_ctx_opt.verify_peer = False
        tls_ctx_opt.alpn_list = ['h2']
        tls_ctx = ClientTlsContext(tls_ctx_opt)
        tls_options = tls_ctx.new_connection_options()
        tls_options.set_server_name("httpbin.org")

        connection = await AIOHttp2ClientConnection.new(
            host_name="httpbin.org",
            port=443,
            tls_connection_options=tls_options
        )
        self.assertTrue(hasattr(connection, 'update_window'),
                        "HTTP/2 Connection missing update_window method")
        self.assertTrue(callable(getattr(connection, 'update_window')),
                        "update_window is not callable")
        await connection.close()

    async def _test_h1_connection_no_update_window_method(self):
        """Test HTTP/1.1 connection does NOT have update_window method"""
        tls_ctx_opt = TlsContextOptions()
        tls_ctx_opt.verify_peer = False
        tls_ctx_opt.alpn_list = ['http/1.1']
        tls_ctx = ClientTlsContext(tls_ctx_opt)
        tls_options = tls_ctx.new_connection_options()
        tls_options.set_server_name("httpbin.org")

        connection = await AIOHttpClientConnection.new(
            host_name="httpbin.org",
            port=443,
            tls_connection_options=tls_options
        )
        self.assertFalse(hasattr(connection, 'update_window'),
                         "HTTP/1.1 Connection should NOT have update_window method")
        await connection.close()

    def test_h2_connection_has_update_window_method(self):
        asyncio.run(self._test_h2_connection_has_update_window_method())

    def test_h1_connection_no_update_window_method(self):
        asyncio.run(self._test_h1_connection_no_update_window_method())

    def test_stream_has_update_window_method(self):
        """Test stream has update_window method"""
        from awscrt.http import HttpClientStreamBase
        self.assertTrue(hasattr(HttpClientStreamBase, 'update_window'),
                        "HttpClientStreamBase missing update_window method")

    async def _test_h2_manual_window_management_happy_path(self):
        """Test HTTP/2 manual window management happy path"""
        tls_ctx_opt = TlsContextOptions()
        tls_ctx_opt.verify_peer = False
        tls_ctx_opt.alpn_list = ['h2']
        tls_ctx = ClientTlsContext(tls_ctx_opt)
        tls_options = tls_ctx.new_connection_options()
        tls_options.set_server_name("httpbin.org")

        connection = await AIOHttp2ClientConnection.new(
            host_name="httpbin.org",
            port=443,
            tls_connection_options=tls_options,
            manual_window_management=True,
            initial_window_size=65536
        )

        request = HttpRequest('GET', '/get')
        request.headers.add('host', 'httpbin.org')
        stream = connection.request(request)

        response = Response()
        status_code = await response.collect_response(stream)

        self.assertEqual(200, status_code)
        self.assertGreater(len(response.body), 0, "No data received")
        await connection.close()

    def test_h2_manual_window_management_happy_path(self):
        asyncio.run(self._test_h2_manual_window_management_happy_path())

    async def _test_h1_manual_window_management_happy_path(self):
        """Test HTTP/1.1 manual window management happy path"""
        tls_ctx_opt = TlsContextOptions()
        tls_ctx_opt.verify_peer = False
        tls_ctx_opt.alpn_list = ['http/1.1']
        tls_ctx = ClientTlsContext(tls_ctx_opt)
        tls_options = tls_ctx.new_connection_options()
        tls_options.set_server_name("httpbin.org")

        connection = await AIOHttpClientConnection.new(
            host_name="httpbin.org",
            port=443,
            tls_connection_options=tls_options,
            manual_window_management=True,
            initial_window_size=5,
            read_buffer_capacity=1000
        )

        request = HttpRequest('GET', '/bytes/10')
        request.headers.add('host', 'httpbin.org')
        stream = connection.request(request)

        response = Response()
        status_code = await response.collect_response(stream)

        self.assertEqual(200, status_code)
        self.assertEqual(10, len(response.body))
        await connection.close()

    def test_h1_manual_window_management_happy_path(self):
        asyncio.run(self._test_h1_manual_window_management_happy_path())


if __name__ == '__main__':
    unittest.main()
