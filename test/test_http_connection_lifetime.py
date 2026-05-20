# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import gc
import threading
import unittest
from test import NativeResourceTest
from http.server import HTTPServer, SimpleHTTPRequestHandler
from awscrt.io import ClientBootstrap, DefaultHostResolver, EventLoopGroup
from awscrt.http import HttpClientConnection, HttpRequest


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200, 'OK')
        self.send_header('Content-Length', '5')
        self.end_headers()
        self.wfile.write(b'hello')


class TestConnectionLifetime(NativeResourceTest):
    """Tests for http_connection_binding ref-count based lifetime management.

    Under free-threaded Python (Py_GIL_DISABLED), the capsule destructor
    (application thread) and on_connection_shutdown (event-loop thread) can
    race. These tests exercise both orderings and a stress scenario.
    """
    hostname = 'localhost'
    timeout = 10

    def setUp(self):
        super().setUp()
        self.server = HTTPServer((self.hostname, 0), SilentHandler)
        self.port = self.server.server_address[1]
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()
        super().tearDown()

    def _new_connection(self):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        future = HttpClientConnection.new(
            host_name=self.hostname,
            port=self.port,
            bootstrap=bootstrap)
        return future.result(self.timeout)

    def test_release_before_shutdown(self):
        """Capsule destructor fires first, then shutdown callback."""
        connection = self._new_connection()
        shutdown_future = connection.shutdown_future

        del connection
        gc.collect()

        shutdown_future.result(self.timeout)

    def test_shutdown_before_release(self):
        """Shutdown callback fires first (via close), then capsule destructor."""
        connection = self._new_connection()
        shutdown_future = connection.shutdown_future

        connection.close()
        shutdown_future.result(self.timeout)

        del connection
        gc.collect()

    def test_concurrent_release_and_shutdown_stress(self):
        """Stress: race capsule destructor against shutdown from many threads.

        Under Py_GIL_DISABLED, the old two-bool approach would double-free.
        With atomic ref-counting, exactly one path destroys the binding.
        """
        iterations = 50
        errors = []

        def release_connection(conn):
            try:
                del conn
                gc.collect()
            except Exception as e:
                errors.append(e)

        for _ in range(iterations):
            connection = self._new_connection()
            shutdown_future = connection.shutdown_future

            connection.close()

            t = threading.Thread(target=release_connection, args=(connection,))
            del connection
            t.start()

            shutdown_future.result(self.timeout)
            t.join(self.timeout)

        self.assertEqual([], errors)


if __name__ == '__main__':
    unittest.main()
