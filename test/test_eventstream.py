# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.eventstream import *
from awscrt.io import ClientBootstrap, DefaultHostResolver, EventLoopGroup
from queue import Queue
from test import NativeResourceTest, TIMEOUT
import time
from uuid import UUID, uuid4


class TestHeaders(NativeResourceTest):
    def test_bool_true(self):
        name = 'truthy'
        value = True
        h = EventStreamHeader.from_bool(name, value)
        self.assertIs(EventStreamHeaderType.BOOL_TRUE, h.type)
        self.assertEqual(value, h.value_as_bool())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_bool_false(self):
        name = 'falsey'
        value = False
        h = EventStreamHeader.from_bool(name, value)
        self.assertIs(EventStreamHeaderType.BOOL_FALSE, h.type)
        self.assertEqual(value, h.value_as_bool())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_byte(self):
        name = 'bytey'
        value = 127
        h = EventStreamHeader.from_byte(name, value)
        self.assertIs(EventStreamHeaderType.BYTE, h.type)
        self.assertEqual(value, h.value_as_byte())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, EventStreamHeader.from_byte, 'too-big', 128)
        self.assertRaises(ValueError, EventStreamHeader.from_byte, 'too-small', -129)

    def test_int16(self):
        name = 'sweet16'
        value = 32000
        h = EventStreamHeader.from_int16(name, value)
        self.assertIs(EventStreamHeaderType.INT16, h.type)
        self.assertEqual(value, h.value_as_int16())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, EventStreamHeader.from_int16, 'too-big', 64000)
        self.assertRaises(ValueError, EventStreamHeader.from_int16, 'too-small', -64000)

    def test_int32(self):
        name = 'win32'
        value = 2000000000
        h = EventStreamHeader.from_int32(name, value)
        self.assertIs(EventStreamHeaderType.INT32, h.type)
        self.assertEqual(value, h.value_as_int32())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, EventStreamHeader.from_int32, 'too-big', 4000000000)
        self.assertRaises(ValueError, EventStreamHeader.from_int32, 'too-small', -4000000000)

    def test_int64(self):
        name = 'N64'
        value = 9223372036854775807
        h = EventStreamHeader.from_int64(name, value)
        self.assertIs(EventStreamHeaderType.INT64, h.type)
        self.assertEqual(value, h.value_as_int64())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

        self.assertRaises(ValueError, EventStreamHeader.from_int32, 'too-big', 18000000000000000000)
        self.assertRaises(ValueError, EventStreamHeader.from_int32, 'too-small', -18000000000000000000)

    def test_byte_buf(self):
        name = 'buffy'
        value = bytes(range(0, 256)) * 100
        h = EventStreamHeader.from_byte_buf(name, value)
        self.assertIs(EventStreamHeaderType.BYTE_BUF, h.type)
        self.assertEqual(value, h.value_as_byte_buf())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_string(self):
        name = 'stringy'
        value = 'abcdefghijklmnopqrstuvwxyz' * 100
        h = EventStreamHeader.from_string(name, value)
        self.assertIs(EventStreamHeaderType.STRING, h.type)
        self.assertEqual(value, h.value_as_string())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_timestamp(self):
        name = 'timeywimey'
        value = time.time()
        h = EventStreamHeader.from_timestamp(name, value)
        self.assertIs(EventStreamHeaderType.TIMESTAMP, h.type)
        # compare with delta, since protocol uses int instead of float
        self.assertAlmostEqual(value, h.value_as_timestamp(), delta=1.0)
        self.assertAlmostEqual(value, h.value, delta=1.0)
        self.assertEqual(name, h.name)

    def test_uuid(self):
        name = 'davuuid'
        value = UUID('01234567-89ab-cdef-0123-456789abcdef')
        h = EventStreamHeader.from_uuid(name, value)
        self.assertIs(EventStreamHeaderType.UUID, h.type)
        self.assertEqual(value, h.value_as_uuid())
        self.assertEqual(value, h.value)
        self.assertEqual(name, h.name)

    def test_wrong_type(self):
        h = EventStreamHeader.from_bool('truthy', True)
        self.assertRaises(TypeError, h.value_as_byte)
        self.assertRaises(TypeError, h.value_as_int16)
        self.assertRaises(TypeError, h.value_as_int32)
        self.assertRaises(TypeError, h.value_as_int64)
        self.assertRaises(TypeError, h.value_as_byte_buf)
        self.assertRaises(TypeError, h.value_as_string)
        self.assertRaises(TypeError, h.value_as_timestamp)
        self.assertRaises(TypeError, h.value_as_uuid)

        h = EventStreamHeader.from_int32('32', 32)
        self.assertRaises(TypeError, h.value_as_bool)
        self.assertRaises(TypeError, h.value_as_int64)


class EventRecord:
    def __init__(self):
        self.setup_call = None
        self.shutdown_call = None
        self.message_calls = Queue()
        self.failure = None


class SimpleHandler(EventStreamRpcClientConnectionHandler):
    def __init__(self):
        super().__init__()
        self.record = EventRecord()

    def on_connection_setup(self, **kwargs):
        if self.record.setup_call is not None:
            self.record.failure = "setup can only fire once"
        self.record.setup_call = {}

    def on_connection_shutdown(self, reason, **kwargs):
        if self.record.setup_call is None:
            self.record.failure = "if setup doesn't fire, shutdown shouldn't fire"
        if self.record.shutdown_call is not None:
            self.record.failure = "shutdown can only fire once"
        self.record.shutdown_call = {'reason': reason}

    def on_protocol_message(self, headers, payload, message_type, flags, **kwargs):
        if self.record.setup_call is None:
            self.record.failure = "setup must fire before messages"
        if self.record.shutdown_call is not None:
            self.record.failure = "messages cannot fire after shutdown"
        self.record.message_calls.put(
            {'headers': headers, 'payload': payload, 'message_type': message_type, 'flags': flags})


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
        self.assertIsNone(handler.record.setup_call)
        self.assertIsNone(handler.record.shutdown_call)
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
        self.assertIsNotNone(handler.record.setup_call)
        self.assertTrue(handler.connection.is_open())
        self.assertIsNone(handler.record.shutdown_call)

        # close
        shutdown_future = handler.connection.close()
        self.assertIsNone(shutdown_future.exception(TIMEOUT))
        self.assertIsNotNone(handler.record.shutdown_call)
        self.assertIsNone(handler.record.shutdown_call['reason'])

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
        self.assertIsNone(
            record.shutdown_call,
            "on_connection_shutdown shouldn't fire if handler is garbage collected before connection finishes shutdown")

        self.assertIsNone(record.failure)

    def test_echo(self):
        self.skipTest("Skipping until we have permanent echo server")
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = SimpleHandler()
        connect_future = EventStreamRpcClientConnection.connect(
            handler=handler,
            host_name="127.0.0.1",
            port=8033,
            bootstrap=bootstrap)

        self.assertIsNone(connect_future.exception(TIMEOUT))

        # send CONNECT msg
        msg_future = handler.connection.send_protocol_message(
            message_type=EventStreamRpcMessageType.CONNECT,
            headers=[EventStreamHeader.from_string(':version', '0.1.0'),
                     EventStreamHeader.from_string('client-name', 'accepted.testy_mc_testerson')])

        self.assertIsNone(msg_future.exception(TIMEOUT))

        # wait to receive CONNECT_ACK
        msg = handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertIs(EventStreamRpcMessageType.CONNECT_ACK, msg['message_type'])
        self.assertTrue(EventStreamRpcMessageFlag.CONNECTION_ACCEPTED & msg['flags'])

        # send PING msg, server will echo back its headers and payload in the PING_RESPONSE.
        # test every single header type
        echo_headers = [
            EventStreamHeader.from_bool('echo-true', True),
            EventStreamHeader.from_bool('echo-false', False),
            EventStreamHeader.from_byte('echo-byte', 127),
            EventStreamHeader.from_int16('echo-int16', 32000),
            EventStreamHeader.from_int32('echo-int32', 2000000000),
            EventStreamHeader.from_int64('echo-int64', 999999999999),
            EventStreamHeader.from_byte_buf('echo-byte-buf', b'\x00\xff\x0f\xf0'),
            EventStreamHeader.from_string('echo-string', 'noodles'),
            EventStreamHeader.from_timestamp('echo-timestamp', time.time()),
            EventStreamHeader.from_uuid('echo-uuid', UUID('01234567-89ab-cdef-0123-456789abcdef')),
        ]
        echo_payload = b'\x00\xDE\xAD\xBE\xEF'
        msg_future = handler.connection.send_protocol_message(
            message_type=EventStreamRpcMessageType.PING,
            headers=echo_headers,
            payload=echo_payload)

        self.assertIsNone(msg_future.exception(TIMEOUT))

        # wait to receive PING_RESPONSE, which should echo what we sent
        msg = handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertIs(EventStreamRpcMessageType.PING_RESPONSE, msg['message_type'])
        for sent_header in echo_headers:
            recv_header = next(x for x in msg['headers'] if x.name.lower() == sent_header.name.lower())
            self.assertEqual(sent_header.type, recv_header.type)
            self.assertEqual(sent_header.value, recv_header.value)
        self.assertEqual(echo_payload, msg['payload'])

        self.assertIsNone(handler.record.failure)
