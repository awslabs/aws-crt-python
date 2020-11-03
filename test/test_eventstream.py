# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.eventstream import EventStreamRpcClientConnection, EventStreamRpcClientConnectionHandler
from awscrt.io import ClientBootstrap, DefaultHostResolver, EventLoopGroup
from test import NativeResourceTest, TIMEOUT


class EventRecord:
    def __init__(self):
        self.setup_calls = []
        self.shutdown_calls = []
        self.message_calls = []
        self.failure = None


class SimpleHandler(EventStreamRpcClientConnectionHandler):
    def __init__(self):
        super().__init__()
        self.record = EventRecord()

    def on_connection_setup(self, **kwargs):
        if len(self.record.setup_calls) > 0:
            self.record.failure = "setup can only fire once"
        self.record.setup_calls.append({})

    def on_connection_shutdown(self, reason, **kwargs):
        if len(self.record.setup_calls) == 0:
            self.record.failure = "if setup doesn't fire, shutdown shouldn't fire"
        if len(self.record.shutdown_calls) > 0:
            self.record.failure = "shutdown can only fire once"
        self.record.shutdown_calls.append({'reason': reason})

    def on_protocol_message(self, **kwargs):
        if len(self.record.setup_calls) == 0:
            self.record.failure = "setup must fire before messages"
        if len(self.record.shutdown_calls) > 0:
            self.record.failure = "messages cannot fire after shutdown"
        self.record.message_calls.append(kwargs)


class TestClient(NativeResourceTest):
    def test_connect_failure(self):
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
        self.assertEqual(0, len(handler.record.setup_calls))
        self.assertEqual(0, len(handler.record.shutdown_calls))
        self.assertIsNone(handler.record.failure)

    def test_connect_success(self):
        self.skipTest("Skipping until we have permanent echo server")
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = SimpleHandler()
        future = EventStreamRpcClientConnection.connect(
            handler=handler,
            host_name="127.0.0.1",
            port=8033,
            bootstrap=bootstrap)

        self.assertIsNone(future.exception(TIMEOUT))
        self.assertEqual(1, len(handler.record.setup_calls))
        self.assertTrue(handler.connection.is_open())
        self.assertEqual(0, len(handler.record.shutdown_calls))

        # close
        shutdown_future = handler.connection.close()
        self.assertIsNone(shutdown_future.exception(TIMEOUT))
        self.assertEqual(1, len(handler.record.shutdown_calls))
        self.assertIsNone(handler.record.shutdown_calls[0]['reason'])

        self.assertIsNone(handler.record.failure)

    def test_closes_on_zero_refcount(self):
        self.skipTest("Skipping until we have permanent echo server")
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = SimpleHandler()
        future = EventStreamRpcClientConnection.connect(
            handler=handler,
            host_name="127.0.0.1",
            port=8033,
            bootstrap=bootstrap)

        # connection should succeed
        self.assertIsNone(future.exception(TIMEOUT))

        # grab pointers to stuff that will tell us about how shutdown went,
        record = handler.record
        shutdown_future = handler.connection.shutdown_future

        # connection should shut itself down when all references are released.
        # the shutdown_future should complete, but the handler's shutdown
        # callback should not fire in this test because the handler has been deleted.
        del handler
        self.assertIsNone(shutdown_future.exception(TIMEOUT))
        self.assertEqual(
            0,
            len(record.shutdown_calls),
            "on_connection_shutdown shouldn't fire if handler is garbage collected before connection finishes shutdown")

        self.assertIsNone(record.failure)
