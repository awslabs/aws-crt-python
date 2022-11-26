# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import asyncio
from awscrt.io import *
from awscrt.websocket import *
from concurrent.futures import Future
from contextlib import closing
import gc
import logging
import socket
from test import NativeResourceTest
import threading
from time import sleep

# using a 3rdparty websocket library for the server
import websockets.server as websockets_server_3rdparty

TIMEOUT = 10.0  # seconds

# uncomment this for logging from the 3rdparty websockets server
# logging.basicConfig(format="%(message)s", level=logging.DEBUG)

# uncomment this for logging from our websockets client
# init_logging(LogLevel.Trace, 'stderr')


class WebSocketServer:
    # Usage: Instantiate this WebSocketServer class in a `with` block.
    # On creation, it starts a thread to run the asyncio server.
    # Exiting the `with` block will cause the server to close and the thread to end.
    #
    # Details: We use the 3rdparty "websockets" library to host a local server
    # that we can test our client against.
    # This 3rdparty library has an asyncio API.
    # Our client does not have an asyncio API.
    # Since it's touch to mix code that uses asyncio with stuff that doesn't,
    # Since asyncio APIs don't mix well with non-asyncio stuff,
    # we launch a thread to run all the asyncio stuff.

    def __init__(self, host, port):
        self._host = host
        self._port = port
        # We use an old-fashioned thread-safe Event to signal the main thread
        # that the asyncio server thread has finished startup.
        self._server_started_event = threading.Event()
        self._server_thread = threading.Thread(target=self._run_server_thread)

    def __enter__(self):
        # main thread is entering the `with` block: start the server...
        self._server_thread.start()

        # don't return until the server signals that it's started up and is listening for connections
        assert self._server_started_event.wait(TIMEOUT)

    def __exit__(self, exc_type, exc_value, exc_tb):
        # main thread is exiting the `with` block: tell the server to stop...

        # asyncio events aren't actually thread-safe, so we can't simply call set() from here.
        # we need to call it from the loop.
        self._server_loop.call_soon_threadsafe(self._server_stop_event.set)

        # don't return until the server thread exits
        self._server_thread.join(TIMEOUT)
        # check whether thread really exited, or we just timed out
        assert (self._server_thread.is_alive() == False)

    def _run_server_thread(self):
        asyncio.run(self._run_asyncio_server())

    async def _run_asyncio_server(self):
        # store things the main thread will need later, so it can signal us to stop...
        self._server_loop = asyncio.get_running_loop()
        self._server_stop_event = asyncio.Event()

        # this coroutine runs the server until the _stop_event fires
        async with websockets_server_3rdparty.serve(self._run_connection, self._host, self._port) as server:
            # signal that server has started up
            self._server_started_event.set()
            # wait for the signal that we should stop
            await self._server_stop_event.wait()

    async def _run_connection(self, server_connection: websockets_server_3rdparty.WebSocketServerProtocol):
        # this coroutine runs once for each connection to the server
        # when this coroutine exits, the connection gets shut down
        try:
            # await each message...
            async for msg in server_connection:
                # print(f"server msg: {msg}")
                pass

        except Exception:
            # an exception is raised when the connection ends,
            # even if the connection ends cleanly, so just swallow it
            pass


class TestClient(NativeResourceTest):
    def setUp(self):
        super().setUp()
        # Note: specifying IPV4 "127.0.0.1", instead of "localhost".
        # "localhost" leads to some machines hitting errors attempting to bind IPV6 addresses.
        self.host = '127.0.0.1'
        self.port = self._find_free_port()

    def _find_free_port(self):
        # find a free port by binding a temporary socket to port 0
        # and seeing what OS gives us
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.bind(('localhost', 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return sock.getsockname()[1]

    def test_create_handshake_request(self):
        request = create_handshake_request(host='localhost', path='/mypath')
        self.assertEqual('GET', request.method)
        self.assertEqual('/mypath', request.path)
        # check that request has some of the necessary headers
        self.assertIn(('Host', 'localhost'), request.headers)
        self.assertIn(('Upgrade', 'websocket'), request.headers)

    def test_connect(self):
        # test a simple successful connection
        with WebSocketServer(self.host, self.port) as server:
            setup_future = Future()
            shutdown_future = Future()

            connect(
                host=self.host,
                port=self.port,
                handshake_request=create_handshake_request(host=self.host),
                on_connection_setup=lambda x: setup_future.set_result(x),
                on_connection_shutdown=lambda x: shutdown_future.set_result(x))

            # wait for on_connection_setup() to fire
            setup_data: OnConnectionSetupData = setup_future.result(TIMEOUT)

            # check that we had a successful connection
            self.assertIsNone(setup_data.exception)
            self.assertIsNotNone(setup_data.websocket)
            # should be a 101 response
            self.assertEqual(101, setup_data.handshake_response_status)
            # check for response header we know should be there
            self.assertIn(("Upgrade", "websocket"), setup_data.handshake_response_headers)

            # now close the WebSocket
            setup_data.websocket.close()

            # wait for on_connection_shutdown() to fire
            shutdown_data: OnConnectionShutdownData = shutdown_future.result(TIMEOUT)
            self.assertIsNone(shutdown_data.exception, "Should have shut down cleanly")

    def test_closes_on_zero_refcount(self):
        # test that a WebSocket shuts down if it's garbage-collected while the connection is still open
        with WebSocketServer(self.host, self.port) as server:
            setup_future = Future()
            shutdown_future = Future()

            connect(
                host=self.host,
                port=self.port,
                handshake_request=create_handshake_request(host=self.host),
                on_connection_setup=lambda x: setup_future.set_result(x),
                on_connection_shutdown=lambda x: shutdown_future.set_result(x))

            # wait for on_connection_setup to fire
            websocket = setup_future.result(TIMEOUT).websocket

            # ensure the connection stays alive while we hold a reference
            gc.collect()
            sleep(0.5)
            self.assertFalse(shutdown_future.done())

            # drop any references to the WebSocket, and ensure the connection shuts down
            del setup_future
            del websocket
            gc.collect()
            shutdown_data: OnConnectionShutdownData = shutdown_future.result(TIMEOUT)
            self.assertIsNone(shutdown_data.exception, "Should have shut down cleanly")

    def test_connect_failure_without_response(self):
        # test a connection that fails before an HTTP response is received

        # the connection will fail because we're not running a server for this test
        setup_future = Future()
        shutdown_future = Future()

        connect(
            host=self.host,
            port=self.port,
            handshake_request=create_handshake_request(host=self.host),
            on_connection_setup=lambda x: setup_future.set_result(x),
            on_connection_shutdown=lambda x: shutdown_future.set_result(x))

        # wait for on_connection_setup to fire
        setup_data: OnConnectionSetupData = setup_future.result(TIMEOUT)
        self.assertIsNone(setup_data.websocket)
        self.assertIsNotNone(setup_data.exception)

        # nothing responded, so there should be no "handshake response"
        self.assertIsNone(setup_data.handshake_response_status)
        self.assertIsNone(setup_data.handshake_response_headers)

        # ensure that on_connection_shutdown does NOT fire
        sleep(0.5)
        self.assertFalse(shutdown_future.done(), "on_connection_shutdown should not have fired")

    def test_connect_failure_with_response(self):
        # test a connection that fails due an HTTP response rejecting the connection
        with WebSocketServer(self.host, self.port) as server:
            setup_future = Future()

            # remove necessary headers, so the server will reject this request
            bad_request = create_handshake_request(host=self.host)
            bad_request.headers.remove('Upgrade')  # "Upgrade: websocket"
            bad_request.headers.remove('Connection')  # "Connection: Upgrade"

            connect(
                host=self.host,
                port=self.port,
                handshake_request=bad_request,
                on_connection_setup=lambda x: setup_future.set_result(x))

            # wait for on_connection_setup to fire
            setup_data: OnConnectionSetupData = setup_future.result(TIMEOUT)
            self.assertIsNone(setup_data.websocket)
            self.assertIsNotNone(setup_data.exception)
            self.assertEqual("AWS_ERROR_HTTP_WEBSOCKET_UPGRADE_FAILURE", setup_data.exception.name)

            # check the HTTP response data
            self.assertGreaterEqual(setup_data.handshake_response_status, 400)
            self.assertIsNotNone(setup_data.handshake_response_headers)

    def test_close_is_idempotent(self):
        # test that it's always safe to call WebSocket.close()
        with WebSocketServer(self.host, self.port) as server:
            setup_future = Future()
            shutdown_future = Future()

            connect(
                host=self.host,
                port=self.port,
                handshake_request=create_handshake_request(host=self.host),
                on_connection_setup=lambda x: setup_future.set_result(x),
                on_connection_shutdown=lambda x: shutdown_future.set_result(x))

            # wait for on_connection_setup to fire
            websocket = setup_future.result(TIMEOUT).websocket

            # now call close() A BUNCH of times...
            close_futures = []

            # ...before shutdown has started!
            close_futures.append(websocket.close())
            close_futures.append(websocket.close())

            # ...while shutdown is happening!
            sleep(0.0000001)
            close_futures.append(websocket.close())
            close_futures.append(websocket.close())

            # wait for shutdown.
            shutdown_data: OnConnectionShutdownData = shutdown_future.result(TIMEOUT)
            self.assertIsNone(shutdown_data.exception, "Shutdown should have been clean")

            # ...and after shutdown has already occurred!
            close_futures.append(websocket.close())
            close_futures.append(websocket.close())

            # now make sure the futures returned by close() are all complete
            for close_future in close_futures:
                self.assertTrue(close_future.done())
