# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import asyncio
from awscrt.io import *
from awscrt.websocket import *
from concurrent.futures import Future
import logging
from socket import AddressFamily
from test import NativeResourceTest

# using a 3rdparty websocket library for the server
import websockets.server as websockets_server_3rdparty

TIMEOUT = 10

# logging.basicConfig(
#     format="%(message)s",
#     level=logging.DEBUG,
# )
# init_logging(LogLevel.Trace, 'stderr')


class ClientHandler:
    def __init__(self):
        self.connect_future = Future()

    def on_connection_setup(self, data: OnConnectionSetupData):
        print(f"SETUP: ${data}")
        self.connect_future.set_result(data)


class TestClient(NativeResourceTest):

    def test_create_handshake_request(self):
        request = create_handshake_request(host='localhost', path='/mypath')
        self.assertEqual('GET', request.method)
        self.assertEqual('/mypath', request.path)
        self.assertIn(('Host', 'localhost'), request.headers)
        self.assertIn(('Upgrade', 'websocket'), request.headers)

    async def _server_connection_main(self, server_connection: websockets_server_3rdparty.WebSocketServerProtocol):
        for msg in server_connection:
            pass

    async def _start_server(self):
        # OS will pick a port if you pass 0
        self.server = await websockets_server_3rdparty.serve(self._server_connection_main, 'localhost', port=0)

        # now find out which port is being used so client can connect
        self.port = self.server.sockets[1].getsockname()[1]  # TODO why socket[1] ??

    def test_connect(self):
        asyncio.run(self._start_server())

        # create HTTP request used to establish websocket connection
        request = create_handshake_request(host='localhost', path='/')

        client_handler = ClientHandler()
        WebSocket.connect_client(
            host='localhost',
            port=self.port,
            handshake_request=request,
            on_connection_setup=client_handler.on_connection_setup)

        # wait for on_connection_setup() to fire, which stores the results in a Future
        connect_data = client_handler.connect_future.result(timeout=TIMEOUT)

        # check that we had a successful connection
        self.assertIsNone(connect_data.exception)
        websocket = connect_data.websocket
        self.assertIsNotNone(websocket)
        # should be a 101 response
        self.assertEqual(101, connect_data.handshake_response_status)
        # check a header we know should be there
        self.assertIn(("Upgrade", "websocket"), connect_data.handshake_response_headers)
        # successful response should have no body
        self.assertIsNone(connect_data.handshake_response_body)
