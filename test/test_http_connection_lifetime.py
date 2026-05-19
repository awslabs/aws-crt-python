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

    These tests exercise the two-path destruction handshake (capsule destructor
    on application thread + on_connection_shutdown on event-loop thread) to
    verify no double-free occurs after the atomic ref-count fix.
    """
    hostname = 'localhost'
    timeout = 10

    def _start_server(self):
        self.server = HTTPServer((self.hostname, 0), SilentHandler)
        self.port = self.server.server_address[1]
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

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
        """Drop all Python references so capsule destructor fires first,
        then shutdown callback fires. Binding must be destroyed exactly once."""
        self._start_server()
        try:
            connection = self._new_connection()
            shutdown_future = connection.shutdown_future

            # Drop Python reference -> capsule destructor -> s_connection_release
            del connection
            gc.collect()

            # Shutdown callback fires on event-loop thread -> completes the ref pair
            shutdown_future.result(self.timeout)
        finally:
            self._stop_server()

    def test_shutdown_before_release(self):
        """Force shutdown callback to fire first via close(), then drop Python
        reference so capsule destructor fires second."""
        self._start_server()
        try:
            connection = self._new_connection()
            shutdown_future = connection.shutdown_future

            # Trigger shutdown on event-loop thread
            connection.close()
            shutdown_future.result(self.timeout)

            # Now drop Python reference -> capsule destructor fires second
            del connection
            gc.collect()
        finally:
            self._stop_server()

    def test_concurrent_release_and_shutdown_stress(self):
        """Stress test: create many connections and race release against shutdown.

        Creates connections, immediately closes them (triggering shutdown on the
        event-loop thread) and simultaneously drops the Python reference from
        another thread. Under the old bool-flag approach with Py_GIL_DISABLED,
        this would produce double-frees. With atomic ref-counting, exactly one
        path destroys the binding.
        """
        self._start_server()
        try:
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

                # Start close (fires shutdown on event-loop thread)
                connection.close()

                # Concurrently drop the Python reference from another thread
                t = threading.Thread(target=release_connection, args=(connection,))
                del connection
                t.start()

                # Wait for both paths to complete
                shutdown_future.result(self.timeout)
                t.join(self.timeout)

            self.assertEqual([], errors)
        finally:
            self._stop_server()

    def test_multiple_connections_sequential_lifecycle(self):
        """Create and destroy multiple connections sequentially to verify
        no corruption from one connection's destruction affects the next."""
        self._start_server()
        try:
            for _ in range(20):
                connection = self._new_connection()
                self.assertTrue(connection.is_open())

                request = HttpRequest('GET', '/')
                stream = connection.request(request)
                stream.activate()
                stream.completion_future.result(self.timeout)
                del stream
                del request

                shutdown_future = connection.shutdown_future
                del connection
                gc.collect()

                try:
                    shutdown_future.result(self.timeout)
                except Exception:
                    pass
        finally:
            self._stop_server()


if __name__ == '__main__':
    unittest.main()
