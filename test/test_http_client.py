# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt.exceptions
from awscrt.http import HttpClientConnection, HttpClientStream, HttpHeaders, HttpProxyOptions, HttpRequest, HttpVersion, Http2ClientConnection
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, TlsCipherPref
from concurrent.futures import Future, thread
from http.server import HTTPServer, SimpleHTTPRequestHandler
from io import BytesIO
import os
import ssl
from test import NativeResourceTest
import threading
import unittest
from urllib.parse import urlparse
import subprocess
import sys
import socket
import time


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


class TestClient(NativeResourceTest):
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

    def _new_client_connection(self, secure, proxy_options=None, cipher_pref=TlsCipherPref.DEFAULT):
        if secure:
            tls_ctx_opt = TlsContextOptions()
            tls_ctx_opt.cipher_pref = cipher_pref
            tls_ctx_opt.verify_peer = False
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

    def _test_connect(self, secure, cipher_pref=TlsCipherPref.DEFAULT):
        self._start_server(secure)
        try:
            connection = self._new_client_connection(secure, cipher_pref=cipher_pref)

            # close connection
            shutdown_error_from_close_future = connection.close().exception(self.timeout)

            # assert that error was reported via close_future and shutdown callback
            # error should be None (normal shutdown)
            self.assertEqual(None, shutdown_error_from_close_future)
            self.assertFalse(connection.is_open())

        finally:
            self._stop_server()

    def test_connect_http(self):
        self._test_connect(secure=False)

    def test_connect_https(self):
        self._test_connect(secure=True)

    def _test_connection_closes_on_zero_refcount(self, secure):
        # The connection should shut itself down cleanly when the GC collects the HttpClientConnection Python object.
        self._start_server(secure)
        try:
            connection = self._new_client_connection(secure)

            # referencing the shutdown_future does not keep the connection alive
            close_future = connection.shutdown_future

            # This should cause the GC to collect the HttpClientConnection
            del connection

            close_error = close_future.exception(self.timeout)
            self.assertEqual(None, close_error)

        finally:
            self._stop_server()

    def test_connection_closes_on_zero_refcount_http(self):
        self._test_connection_closes_on_zero_refcount(secure=False)

    def test_connection_closes_on_zero_refcount_https(self):
        self._test_connection_closes_on_zero_refcount(secure=True)

    def _test_get(self, secure, proxy_options=None):
        # GET request receives this very file from the server. Super meta.

        # Use HTTP/1.0 in proxy tests or server will keep connection with proxy alive
        # and refuse to shut down for 1 minute at the end of each proxy test
        http_1_0 = proxy_options is not None

        self._start_server(secure, http_1_0)
        try:
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

        finally:
            self._stop_server()

    def test_get_http(self):
        self._test_get(secure=False)

    def test_get_https(self):
        self._test_get(secure=True)

    def _test_shutdown_error(self, secure):
        # Use HTTP/1.0 connection to force a SOCKET_CLOSED error after request completes
        self._start_server(secure, http_1_0=True)
        try:
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

        finally:
            self._stop_server()

    def test_shutdown_error_http(self):
        return self._test_shutdown_error(secure=False)

    def test_shutdown_error_https(self):
        return self._test_shutdown_error(secure=True)

    def _test_put(self, secure):
        # PUT request sends this very file to the server.
        self._start_server(secure)
        try:
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

        finally:
            self._stop_server()

    def test_put_http(self):
        self._test_put(secure=False)

    def test_put_https(self):
        self._test_put(secure=True)

    def _test_stream_lives_until_complete(self, secure):
        # Ensure that stream and connection classes stay alive until work is complete
        self._start_server(secure)
        try:
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

        finally:
            self._stop_server()

    def test_stream_lives_until_complete_http(self):
        self._test_stream_lives_until_complete(secure=False)

    def test_stream_lives_until_complete_https(self):
        self._test_stream_lives_until_complete(secure=True)

    def _test_request_lives_until_stream_complete(self, secure):
        # Ensure HttpRequest and body InputStream stay alive until HttpClientStream completes (regression test)
        self._start_server(secure)
        try:
            connection = self._new_client_connection(secure)

            request = HttpRequest(
                method='PUT',
                path='/test/test_request_refcounts.txt',
                headers=HttpHeaders([('Host', self.hostname), ('Content-Length', '5')]),
                body_stream=BytesIO(b'hello'))

            response = Response()
            http_stream = connection.request(request, response.on_response, response.on_body)

            # HttpClientStream should keep the dependencies (HttpRequest, HttpHeaders, InputStream)
            # alive as long as it needs them
            del request

            http_stream.activate()
            http_stream.completion_future.result(self.timeout)

            self.assertEqual(None, connection.close().result(self.timeout))

        finally:
            self._stop_server()

    def test_request_lives_until_stream_complete_http(self):
        return self._test_request_lives_until_stream_complete(secure=False)

    def test_request_lives_until_stream_complete_https(self):
        return self._test_request_lives_until_stream_complete(secure=True)

    def _test_stream_cleans_up_if_never_activated(self, secure):
        # If a stream is never activated, it should just clean itself up
        self._start_server(secure)
        try:
            connection = self._new_client_connection(secure)
            stream = connection.request(HttpRequest('GET', '/test/test_http_client.py'))
            # note we do NOT activate the stream

            # delete local references, stream should clean itself up, connection should shut itself down
            del stream
            del connection

        finally:
            self._stop_server()

    def test_stream_cleans_up_if_never_activated_http(self):
        self._test_stream_cleans_up_if_never_activated(secure=False)

    def test_stream_cleans_up_if_never_activated_https(self):
        self._test_stream_cleans_up_if_never_activated(secure=True)

    def _new_h2_client_connection(self, url):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        port = url.port
        # only test https
        if port is None:
            port = 443
        tls_ctx_options = TlsContextOptions()
        tls_ctx_options.verify_peer = False  # allow localhost
        tls_ctx = ClientTlsContext(tls_ctx_options)
        tls_conn_opt = tls_ctx.new_connection_options()
        tls_conn_opt.set_server_name(url.hostname)
        tls_conn_opt.set_alpn_list(["h2"])

        connection_future = Http2ClientConnection.new(host_name=url.hostname,
                                                      port=port,
                                                      bootstrap=bootstrap,
                                                      tls_connection_options=tls_conn_opt)
        return connection_future.result(self.timeout)

    def test_h2_client(self):
        url = urlparse("https://d1cz66xoahf9cl.cloudfront.net/http_test_doc.txt")
        connection = self._new_h2_client_connection(url)
        # check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('GET', url.path)
        request.headers.add('host', url.hostname)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body)
        stream.activate()

        # wait for stream to complete (use long timeout, it's a big file)
        stream_completion_result = stream.completion_future.result(80)

        # check result
        self.assertEqual(200, response.status_code)
        self.assertEqual(200, stream_completion_result)
        self.assertEqual(14428801, len(response.body))

        self.assertEqual(None, connection.close().exception(self.timeout))

    def test_h2_manual_write_exception(self):
        url = urlparse("https://d1cz66xoahf9cl.cloudfront.net/http_test_doc.txt")
        connection = self._new_h2_client_connection(url)
        # check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('GET', url.path)
        request.headers.add('host', url.hostname)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body)
        stream.activate()
        exception = None
        try:
            # If the stream is not configured to allow manual writes, this should throw an exception directly
            stream.write_data(BytesIO(b'hello'), False)
        except RuntimeError as e:
            exception = e
        self.assertIsNotNone(exception)

        self.assertEqual(None, connection.close().exception(self.timeout))

    @unittest.skipIf(not TlsCipherPref.PQ_DEFAULT.is_supported(), "Cipher pref not supported")
    def test_connect_pq_default(self):
        self._test_connect(secure=True, cipher_pref=TlsCipherPref.PQ_DEFAULT)


@unittest.skipUnless(os.environ.get('AWS_TEST_LOCALHOST'), 'set env var to run test: AWS_TEST_LOCALHOST')
class TestClientMockServer(NativeResourceTest):

    timeout = 5  # seconds
    p_server = None
    mock_server_url = None

    def setUp(self):
        super().setUp()
        # Start the mock server from the aws-c-http.
        server_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'crt',
            'aws-c-http',
            'tests',
            'py_localhost',
            'server.py')
        python_path = sys.executable
        self.mock_server_url = urlparse("https://localhost:3443/upload_test")
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

    def _new_mock_connection(self):

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

        connection_future = Http2ClientConnection.new(host_name=self.mock_server_url.hostname,
                                                      port=port,
                                                      bootstrap=bootstrap,
                                                      tls_connection_options=tls_conn_opt)
        return connection_future.result(self.timeout)

    def test_h2_mock_server_manual_write(self):
        connection = self._new_mock_connection()
        # check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('POST', self.mock_server_url.path)
        request.headers.add('host', self.mock_server_url.hostname)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body, manual_write=True)
        stream.activate()
        exception = None
        try:
            # If the stream is not configured to allow manual writes, this should throw an exception directly
            f = stream.write_data(BytesIO(b'hello'), False)
            f.result(self.timeout)
            stream.write_data(BytesIO(b'he123123'), False)
            stream.write_data(None, False)
            stream.write_data(BytesIO(b'hello'), True)
        except RuntimeError as e:
            exception = e
        self.assertIsNone(exception)
        stream_completion_result = stream.completion_future.result(80)
        # check result
        self.assertEqual(200, response.status_code)
        self.assertEqual(200, stream_completion_result)
        print(response.body)

        self.assertEqual(None, connection.close().exception(self.timeout))

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

    def test_h2_mock_server_manual_write_read_exception(self):
        connection = self._new_mock_connection()
        # check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('POST', self.mock_server_url.path)
        request.headers.add('host', self.mock_server_url.hostname)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body, manual_write=True)
        stream.activate()
        exception = None
        data = self.DelayStream(bad_read=True)
        try:
            f = stream.write_data(data, False)
            f.result(self.timeout)
        except Exception as e:
            # future will raise the exception from the write_data call.
            exception = e
        self.assertIsNotNone(exception)
        # stream will complete with same exception.
        stream_completion_exception = stream.completion_future.exception()
        self.assertIsNotNone(stream_completion_exception)
        # assert that the exception is the same as the one we got from write_data.
        self.assertEqual(str(exception), str(stream_completion_exception))
        self.assertEqual(None, connection.close().exception(self.timeout))

    def test_h2_mock_server_manual_write_lifetime(self):
        connection = self._new_mock_connection()
        # check we set an h2 connection
        self.assertEqual(connection.version, HttpVersion.Http2)

        request = HttpRequest('POST', self.mock_server_url.path)
        request.headers.add('host', self.mock_server_url.hostname)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body, manual_write=True)
        stream.activate()
        exception = None
        data = self.DelayStream(bad_read=False)
        try:
            f = stream.write_data(data, False)
            # make sure when the python object was dropped, things are still ok
            del data
            f.result(self.timeout)
            f = stream.write_data(None, True)
            f.result(self.timeout)
        except Exception as e:
            # future will raise the exception from the write_data call.
            exception = e
        self.assertIsNone(exception)
        # stream will complete with another exception.
        stream.completion_future.result()
        self.assertEqual(None, connection.close().exception(self.timeout))


if __name__ == '__main__':
    unittest.main()
