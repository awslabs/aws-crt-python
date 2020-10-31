# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.eventstream import EventStreamRpcClientConnection, EventStreamRpcClientConnectionHandler
from awscrt.io import ClientBootstrap, DefaultHostResolver, EventLoopGroup
from test import NativeResourceTest, TIMEOUT


class SimpleHandler(EventStreamRpcClientConnectionHandler):
    def __init__(self):
        self.is_setup = False
        self.is_shutdown = False
        self.shutdown_reason = None
        self.protocol_messages = []

    def on_setup(self, **kwargs):
        self.is_setup = True

    def on_shutdown(self, reason, **kwargs):
        self.is_shutdown = True
        self.shutdown_reason = reason

    def on_protocol_message(self, **kwargs):
        self.protocol_messages.append("TODO")


class TestClient(NativeResourceTest):
    def test_failed_connect(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = SimpleHandler()
        future = EventStreamRpcClientConnection.connect(
            handler=handler,
            host_name="fake",
            port=99,
            bootstrap=bootstrap)

        failure = future.exception(TIMEOUT)
        self.assertTrue(isinstance(failure, Exception))
        self.assertFalse(handler.is_setup)
        self.assertFalse(handler.is_shutdown)
