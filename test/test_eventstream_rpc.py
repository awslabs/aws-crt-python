# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.eventstream import *
from awscrt.eventstream.rpc import *
from awscrt.io import ClientBootstrap, DefaultHostResolver, EventLoopGroup
from queue import Queue
from test import NativeResourceTest, TIMEOUT
import time
from unittest import skipUnless
from uuid import UUID, uuid4

# TODO: setup permanent online echo server we can hit from tests
RUN_LOCALHOST_TESTS = False


class EventRecord:
    def __init__(self):
        self.setup_call = None
        self.shutdown_call = None
        self.message_calls = Queue()
        self.failure = None


class ConnectionHandler(ClientConnectionHandler):
    def __init__(self, fail_test_fn):
        self.record = EventRecord()
        self.fail_test = fail_test_fn
        self.connection = None

    def on_connection_setup(self, connection, error, **kwargs):
        if self.record.setup_call is not None:
            self.fail_test("setup can only fire once")
        self.record.setup_call = {'connection': connection, 'error': error}
        self.connection = connection

    def on_connection_shutdown(self, reason, **kwargs):
        if self.record.setup_call is None:
            self.fail_test("if setup doesn't fire, shutdown shouldn't fire")
        if self.record.setup_call['error'] is not None:
            self.fail_test("shutdown shouldn't fire if setup had an error")
        if self.record.shutdown_call is not None:
            self.fail_test("shutdown can only fire once")
        self.record.shutdown_call = {'reason': reason}

    def on_protocol_message(self, headers, payload, message_type, flags, **kwargs):
        if self.record.setup_call is None:
            self.fail_test("setup must fire before messages")
        if self.record.shutdown_call is not None:
            self.fail_test("messages cannot fire after shutdown")
        self.record.message_calls.put(
            {'headers': headers, 'payload': payload, 'message_type': message_type, 'flags': flags})


class ContinuationRecord:
    def __init__(self):
        self.message_calls = Queue()
        self.close_call = None
        self.failure = None


class ContinuationHandler(ClientContinuationHandler):
    def __init__(self, fail_test_fn):
        self.record = ContinuationRecord()
        self.fail_test = fail_test_fn

    def on_continuation_message(
            self,
            headers,
            payload,
            message_type,
            flags,
            **kwargs):
        if self.record.close_call:
            self.fail_test("messages should not fire after close")
        self.record.message_calls.put(
            {'headers': headers, 'payload': payload, 'message_type': message_type, 'flags': flags})

    def on_continuation_closed(self, **kwargs):
        if self.record.close_call:
            self.fail_test("shutdown can only fire once")
        self.record.close_call = {}


class TestClient(NativeResourceTest):

    def _fail_test_from_callback(self, msg):
        print("ERROR FROM CALLBACK", msg)
        self._failure_from_callback = msg

    def _assertNoFailuresFromCallbacks(self):
        self.assertIsNone(getattr(self, '_failure_from_callback', None))

    def test_connect_failure(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = ConnectionHandler(self._fail_test_from_callback)
        future = ClientConnection.connect(
            handler=handler,
            host_name="fake",
            port=99,
            bootstrap=bootstrap)

        failure = future.exception(TIMEOUT)
        self.assertTrue(isinstance(failure, Exception))
        self.assertIsNotNone(handler.record.setup_call)
        self.assertIsNone(handler.record.setup_call['connection'])
        self.assertTrue(isinstance(handler.record.setup_call['error'], Exception))
        self.assertIsNone(handler.record.shutdown_call)
        self._assertNoFailuresFromCallbacks()

    @skipUnless(RUN_LOCALHOST_TESTS, "Skipping until we have permanent echo server")
    def test_connect_success(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = ConnectionHandler(self._fail_test_from_callback)
        future = ClientConnection.connect(
            handler=handler,
            host_name="127.0.0.1",
            port=8033,
            bootstrap=bootstrap)

        self.assertIsNone(future.exception(TIMEOUT))
        self.assertIsNotNone(handler.record.setup_call)
        self.assertTrue(isinstance(handler.record.setup_call['connection'], ClientConnection))
        self.assertIsNone(handler.record.setup_call['error'])
        self.assertTrue(handler.connection.is_open())
        self.assertIsNone(handler.record.shutdown_call)

        # close
        shutdown_future = handler.connection.close()
        self.assertIsNone(shutdown_future.exception(TIMEOUT))
        self.assertIsNotNone(handler.record.shutdown_call)
        self.assertIsNone(handler.record.shutdown_call['reason'])

        self._assertNoFailuresFromCallbacks()

    @skipUnless(RUN_LOCALHOST_TESTS, "Skipping until we have permanent echo server")
    def test_closes_on_zero_refcount(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = ConnectionHandler(self._fail_test_from_callback)
        future = ClientConnection.connect(
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
        del record.setup_call  # we were storing another reference to connection here
        self.assertIsNone(shutdown_future.exception(TIMEOUT))
        self.assertIsNone(
            record.shutdown_call,
            "on_connection_shutdown shouldn't fire if handler is garbage collected before connection finishes shutdown")

        self._assertNoFailuresFromCallbacks()

    @skipUnless(RUN_LOCALHOST_TESTS, "Skipping until we have permanent echo server")
    def test_echo(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = ConnectionHandler(self._fail_test_from_callback)
        connect_future = ClientConnection.connect(
            handler=handler,
            host_name="127.0.0.1",
            port=8033,
            bootstrap=bootstrap)

        self.assertIsNone(connect_future.exception(TIMEOUT))

        # send CONNECT msg
        msg_future = handler.connection.send_protocol_message(
            message_type=MessageType.CONNECT,
            headers=[Header.from_string(':version', '0.1.0'),
                     Header.from_string('client-name', 'accepted.testy_mc_testerson')])

        self.assertIsNone(msg_future.exception(TIMEOUT))

        # wait to receive CONNECT_ACK
        msg = handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertIs(MessageType.CONNECT_ACK, msg['message_type'])
        self.assertTrue(MessageFlag.CONNECTION_ACCEPTED & msg['flags'])

        # send PING msg, server will echo back its headers and payload in the PING_RESPONSE.
        # test every single header type
        echo_headers = [
            Header.from_bool('echo-true', True),
            Header.from_bool('echo-false', False),
            Header.from_byte('echo-byte', 127),
            Header.from_int16('echo-int16', 32000),
            Header.from_int32('echo-int32', 2000000000),
            Header.from_int64('echo-int64', 999999999999),
            Header.from_byte_buf('echo-byte-buf', b'\x00\xff\x0f\xf0'),
            Header.from_string('echo-string', 'noodles'),
            # utf-8 breaks echo test. don't get response.
            #Header.from_string('echo-string-utf8', '--\u1234--'),
            Header.from_timestamp('echo-timestamp', time.time()),
            Header.from_uuid('echo-uuid', UUID('01234567-89ab-cdef-0123-456789abcdef')),
        ]
        echo_payload = b'\x00\xDE\xAD\xBE\xEF'
        msg_future = handler.connection.send_protocol_message(
            message_type=MessageType.PING,
            headers=echo_headers,
            payload=echo_payload)

        self.assertIsNone(msg_future.exception(TIMEOUT))

        # wait to receive PING_RESPONSE, which should echo what we sent
        msg = handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertIs(MessageType.PING_RESPONSE, msg['message_type'])
        for sent_header in echo_headers:
            recv_header = next(x for x in msg['headers'] if x.name.lower() == sent_header.name.lower())
            self.assertEqual(sent_header.type, recv_header.type)
            self.assertEqual(sent_header.value, recv_header.value)
        self.assertEqual(echo_payload, msg['payload'])

        # use a stream to execute the "EchoMessage" operation,
        # which takes 1 message and responds with 1 message
        stream_handler = ContinuationHandler(self._fail_test_from_callback)
        stream_handler.continuation = handler.connection.new_stream(stream_handler)
        msg_future = stream_handler.continuation.activate(
            operation='awstest#EchoMessage',
            headers=[],
            payload=b'{}',
            message_type=MessageType.APPLICATION_MESSAGE,
            flags=MessageFlag.NONE)

        self.assertIsNone(msg_future.exception(TIMEOUT))

        # wait to receive response, which should end the stream
        msg = stream_handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertEqual(MessageType.APPLICATION_MESSAGE, msg['message_type'])
        self.assertTrue(MessageFlag.TERMINATE_STREAM & msg['flags'])
        self.assertIsNone(stream_handler.continuation.closed_future.exception(TIMEOUT))

        # use a stream to execute the "EchoStreamMessages" operation,
        # which has an empty initial request/response, but then allows further messages
        stream_handler = ContinuationHandler(self._fail_test_from_callback)
        stream_handler.continuation = handler.connection.new_stream(stream_handler)
        msg_future = stream_handler.continuation.activate(
            operation='awstest#EchoStreamMessages',
            headers=[],
            payload=b'{}',
            message_type=MessageType.APPLICATION_MESSAGE,
            flags=MessageFlag.NONE)

        self.assertIsNone(msg_future.exception(TIMEOUT))

        # wait to initial response, which should end the stream
        msg = stream_handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertEqual(MessageType.APPLICATION_MESSAGE, msg['message_type'])
        self.assertFalse(MessageFlag.TERMINATE_STREAM & msg['flags'])

        # send a 2nd message on the stream
        msg_future = stream_handler.continuation.send_message(
            headers=[],
            payload=b'{}',
            message_type=MessageType.APPLICATION_MESSAGE,
            flags=MessageFlag.NONE)

        self.assertIsNone(msg_future.exception(TIMEOUT))

        # wait for 2nd response
        msg = stream_handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertEqual(MessageType.APPLICATION_MESSAGE, msg['message_type'])
        self.assertFalse(MessageFlag.TERMINATE_STREAM & msg['flags'])

        # close connection
        handler.connection.close()
        self.assertIsNone(handler.connection.shutdown_future.exception(TIMEOUT))
        self.assertIsNone(stream_handler.continuation.closed_future.exception(TIMEOUT))

        self._assertNoFailuresFromCallbacks()
