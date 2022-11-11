# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import asyncio
from test import NativeResourceTest
import websockets as websockets3rdparty

TIMEOUT = 10

async def server_main(server_websocket):
    async for msg in server_websocket:
        print(f"server received: ${msg}")

class TestClient(NativeResourceTest):
    def _start_server(self):
            self.server = websockets3rdparty.serve(server_main, 'localhost', port=None)
            self.port = self.server.sockets[0].getsockname()[1]
            print(f"server port:${self.port} - ${self.server}")

    def test_a(self):
        self._start_server()
