# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import asyncio
from awscrt.io import *
from awscrt.websocket import *
from concurrent.futures import Future
from contextlib import closing
import logging
import socket
from test import NativeResourceTest
import threading

# using a 3rdparty websocket library for the server
import websockets.server as websockets_server_3rdparty

TIMEOUT = 10.0  # seconds

# uncomment this for logging from the 3rdparty websockets server
# logging.basicConfig(format="%(message)s", level=logging.DEBUG)

# uncomment this for logging from our websockets client
# init_logging(LogLevel.Trace, 'stderr')


class ClientHandler:
    def __init__(self):
        self.setup_future = Future()

    def on_connection_setup(self, data: OnConnectionSetupData):
        # print(f"SETUP: ${data}")
        self.setup_future.set_result(data)


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
        self._started_event = threading.Event()
        self._thread = threading.Thread(target=self._thread_main)

    def __enter__(self):
        # we're entering the `with` block: start the server...
        self._thread.start()

        # don't return until the server signals that it's started up and is listening for connections
        self._started_event.wait()

    def __exit__(self, exc_type, exc_value, exc_tb):
        # we're exiting the `with` block: tell the server to stop...
        self._stop_event.set()

        # don't return until the server thread exits
        self._thread.join(TIMEOUT)

    def _thread_main(self):
        # run the main asyncio coroutine
        asyncio.run(self._asyncio_main())

    async def _asyncio_main(self):
        self._stop_event = asyncio.Event()

        # this coroutine runs the server until the _stop_event fires
        async with websockets_server_3rdparty.serve(self._run_connection, self._host, self._port) as server:
            # signal that server has started up
            self._started_event.set()
            # wait for the signal that we should stop
            await self._stop_event.wait()

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
        self.host = 'localhost'
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

            http_handshake_request = create_handshake_request(host=self.host, path='/')

            client_handler = ClientHandler()
            connect_client(
                host=self.host,
                port=self.port,
                handshake_request=http_handshake_request,
                on_connection_setup=client_handler.on_connection_setup)

            # wait for on_connection_setup() to fire, which stores the results in a Future
            setup_data = client_handler.setup_future.result(timeout=TIMEOUT)

            # check that we had a successful connection
            self.assertIsNone(setup_data.exception)
            self.assertIsNotNone(setup_data.websocket)
            # should be a 101 response
            self.assertEqual(101, setup_data.handshake_response_status)
            # check for response header we know should be there
            self.assertIn(("Upgrade", "websocket"), setup_data.handshake_response_headers)
            # successful response should have no body
            self.assertIsNone(setup_data.handshake_response_body)

            # drop all references to WebSocket,
            # which should cause it to shut down and clean up
            del client_handler.setup_future
            del setup_data
