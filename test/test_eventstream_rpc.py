# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt import NativeResource
from awscrt.eventstream import *
from awscrt.eventstream.rpc import *
from awscrt.io import (ClientBootstrap, DefaultHostResolver, EventLoopGroup, init_logging, LogLevel)
from awscrt._test import native_memory_usage
import gc
import os
from queue import Queue
from test import NativeResourceTest, TIMEOUT
from threading import Event
import time
from unittest import skipUnless
from uuid import UUID, uuid4
import weakref

# TODO: setup permanent online echo server we can hit from tests
RUN_LOCALHOST_TESTS = os.getenv('EVENTSTREAM_ECHO_TEST')

#init_logging(LogLevel.Trace, 'stderr')


class ConnectionRecord:
    def __init__(self):
        self.setup_call = None
        self.shutdown_call = None
        self.message_calls = Queue()


class ConnectionHandler(ClientConnectionHandler):
    def __init__(self, fail_test_fn):
        self.record = ConnectionRecord()
        self.fail_test = fail_test_fn
        self.connection = None
        # whether to purposefully raise an exception in a callback
        self.raise_during_setup = False

    def on_connection_setup(self, connection, error, **kwargs):
        if self.record.setup_call is not None:
            self.fail_test("setup can only fire once")
        self.record.setup_call = {'connection': connection, 'error': error}
        self.connection = connection
        if self.raise_during_setup:
            raise RuntimeError("Purposefully raising error in callback")

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
        self.close_call = Event()


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
        if self.record.close_call.is_set():
            self.fail_test("messages should not fire after close")
        self.record.message_calls.put(
            {'headers': headers, 'payload': payload, 'message_type': message_type, 'flags': flags})

    def on_continuation_closed(self, **kwargs):
        if self.record.close_call.is_set():
            self.fail_test("shutdown can only fire once")
        self.record.close_call.set()


@skipUnless(RUN_LOCALHOST_TESTS, "Skipping until we have permanent echo server")
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

    def _connect_and_return_weakref(self):
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

        return weakref.ref(handler.connection)

    def test_connection_stays_alive_until_close(self):
        # Currently, eventstream connections do NOT close just because their refcount reaches zero.
        # We *could* make it work this way, but it would take some combo of:
        # 1) handler shutdown callbacks aren't guaranteed to fire,
        #    because handler likely has reference to connection, and we want
        #    them to get GC'd together.
        # 2) OR guarantee shutdown callbacks, but explain the subtleties of
        #    avoiding a strong reference cycle involving the handler.
        #    This is not a typical thing Python programmers need to think about.
        # Seems best to keep it simple and just remind the user at every
        # opportunity that connection must be closed to avoid resource leaks.
        connection_weakref = self._connect_and_return_weakref()

        # wait a moment to see if connection gets cleaned up
        time.sleep(1)
        gc.collect()

        connection = connection_weakref()
        self.assertIsNotNone(connection, "open connection should not have been GC'd")
        self.assertTrue(connection.is_open())

        # ok, now shut it down, (and nuke local reference to connection
        # just to be sure we don't crash if both happen simultaneously)
        shutdown_future = connection.close()
        del connection
        self.assertIsNone(shutdown_future.exception(TIMEOUT))

        # GC should have cleaned it up, now that the connection is closed
        # and no strong references remain
        gc.collect()
        self.assertIsNone(connection_weakref())

        self._assertNoFailuresFromCallbacks()

    def test_setup_callback_exception_closes_connection(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        handler = ConnectionHandler(self._fail_test_from_callback)

        # tell handler to explode during setup callback
        handler.raise_during_setup = True
        connect_future = ClientConnection.connect(
            handler=handler,
            host_name="127.0.0.1",
            port=8033,
            bootstrap=bootstrap)

        # the connect future does actually succeed, since the user's setup
        # callback got a chance to run.
        connect_future.exception(TIMEOUT)

        # but the unhandled exception should cause the connection to die
        shutdown_reason = handler.connection.shutdown_future.exception(TIMEOUT)
        self.assertTrue("CALLBACK_EXCEPTION" in shutdown_reason.name)
        self.assertTrue("CALLBACK_EXCEPTION" in handler.record.shutdown_call['reason'].name)

    def _connect_fully(self):
        # connect, send CONNECT message, receive CONNECT_ACK
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

        return handler

    def test_connection_close_without_waiting_for_completion(self):
        # Regression test: check that it's safe to call close and drop local references,
        # without waiting for close() to complete.
        handler = self._connect_fully()
        handler.connection.close()

    def test_stream_cleans_up_if_never_activated(self):
        # check that there are no resource leaks if a stream/continuation is never activated
        handler = self._connect_fully()

        # create stream, but do not activate it
        stream_handler = ContinuationHandler(self._fail_test_from_callback)
        continuation = handler.connection.new_stream(stream_handler)

        # close connection
        handler.connection.close()
        self.assertIsNone(handler.connection.shutdown_future.exception(TIMEOUT))

        # stream callbacks should not fire because it was never activated
        self.assertFalse(stream_handler.record.close_call.isSet())

        self._assertNoFailuresFromCallbacks()

    def test_stream_message_echo(self):
        # test sending and receiving messages
        handler = self._connect_fully()

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
        continuation = handler.connection.new_stream(stream_handler)
        msg_flushed = Event()

        def on_msg_flush(error, **kwargs):
            msg_flushed.set()

        msg_future = continuation.activate(
            operation='awstest#EchoMessage',
            headers=[],
            payload=b'{}',
            message_type=MessageType.APPLICATION_MESSAGE,
            flags=MessageFlag.NONE,
            on_flush=on_msg_flush)

        self.assertIsNone(msg_future.exception(TIMEOUT))
        self.assertTrue(msg_flushed.wait(TIMEOUT))

        # wait to receive response, which should end the stream
        msg = stream_handler.record.message_calls.get(timeout=TIMEOUT)
        self.assertEqual(MessageType.APPLICATION_MESSAGE, msg['message_type'])
        self.assertTrue(MessageFlag.TERMINATE_STREAM & msg['flags'])
        self.assertIsNone(continuation.closed_future.exception(TIMEOUT))

        # use a stream to execute the "EchoStreamMessages" operation,
        # which has an empty initial request/response, but then allows further messages
        stream_handler = ContinuationHandler(self._fail_test_from_callback)
        continuation = handler.connection.new_stream(stream_handler)
        msg_future = continuation.activate(
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
        msg_future = continuation.send_message(
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
        self.assertIsNone(continuation.closed_future.exception(TIMEOUT))

        self._assertNoFailuresFromCallbacks()

    def _start_request_and_drop_local_references(self, connection):
        # use a stream to execute the "EchoMessage" operation,
        # which takes 1 message and responds with 1 message
        stream_handler = ContinuationHandler(self._fail_test_from_callback)
        continuation = connection.new_stream(stream_handler)
        msg_future = continuation.activate(
            operation='awstest#EchoMessage',
            headers=[],
            payload=b'{}',
            message_type=MessageType.APPLICATION_MESSAGE,
            flags=MessageFlag.NONE)

        return (continuation.closed_future, stream_handler.record)

    def test_stream_stays_alive_until_close(self):
        # Test checks that stream stays alive, and all callbacks fire,
        # even if there are no local references to stream or its handler.
        handler = self._connect_fully()

        # create new stream and handler, and send request, but don't get back
        # anything that keeps a reference to these things.
        # function returns items that should show side-effects of the
        # request/response continuation to operate to completion.
        # If this test fails, it's because something got GC'd too early and all
        # the callbacks couldn't fire
        stream_closed_future, stream_record = self._start_request_and_drop_local_references(handler.connection)

        # wait to receive response, which should end the stream
        msg = stream_record.message_calls.get(timeout=TIMEOUT)

        # close connection
        handler.connection.close()
        self.assertIsNone(handler.connection.shutdown_future.exception(TIMEOUT))
        self.assertTrue(stream_record.close_call.wait(timeout=TIMEOUT))
        self.assertIsNone(stream_closed_future.result(timeout=TIMEOUT))

        self._assertNoFailuresFromCallbacks()

    def test_stream_cleans_up_on_close(self):
        # ensure that a stream cleans up immediately after it's closed and references to it are dropped
        handler = self._connect_fully()

        # use function to create and run stream.
        # if we just did it in loop below, local references would stick around
        # and show up when we checked for leaks
        def _run_stream_operation():
            stream_handler = ContinuationHandler(self._fail_test_from_callback)
            continuation = handler.connection.new_stream(stream_handler)
            continuation.activate(
                operation='awstest#EchoMessage',
                headers=[],
                payload=b'{}',
                message_type=MessageType.APPLICATION_MESSAGE,
                flags=MessageFlag.NONE)
            self.assertTrue(stream_handler.record.close_call.wait(TIMEOUT))

        living_resources_at_start = len(NativeResource._living)
        native_mem_usage_at_start = native_memory_usage()

        # run a few streams
        for i in range(10):
            _run_stream_operation()
            gc.collect()
            self.assertEqual(living_resources_at_start, len(NativeResource._living))
            self.assertEqual(native_mem_usage_at_start, native_memory_usage())

        handler.connection.close().result(TIMEOUT)
        self._assertNoFailuresFromCallbacks()

    def test_stream_reference_can_outlive_connection(self):
        # Regression test. Ensure we don't crash if a stream reference stays alive
        # after connection has been closed and references to connection have been dropped
        connection_handler = self._connect_fully()

        # run stream and keep its reference around
        stream_handler = ContinuationHandler(self._fail_test_from_callback)
        continuation = connection_handler.connection.new_stream(stream_handler)
        continuation.activate(
            operation='awstest#EchoMessage',
            headers=[],
            payload=b'{}',
            message_type=MessageType.APPLICATION_MESSAGE,
            flags=MessageFlag.NONE)
        self.assertTrue(stream_handler.record.close_call.wait(TIMEOUT))

        # close connection and nuke local references
        connection_handler.connection.close().result(TIMEOUT)
        connection_weakref = weakref.ref(connection_handler.connection)
        del connection_handler
        gc.collect()

        del stream_handler
        del continuation
        gc.collect()

    def test_on_closed_deadlock_regression(self):
        # ensure that during the on_closed() callback of the first stream,
        # we can activate a second stream without deadlocking
        handler = self._connect_fully()

        # create 2 streams but don't activate yet
        first_stream_handler = DeadlockStreamHandler(handler.connection)
        first_stream = handler.connection.new_stream(first_stream_handler)

        second_stream_handler = ContinuationHandler(self._fail_test_from_callback)
        second_stream = handler.connection.new_stream(second_stream_handler)

        # activate first stream with message that closes the stream
        # from the on_closed() callback it will activate the second stream
        first_stream_handler.second_stream = second_stream
        first_stream.activate(operation="first",
                              message_type=MessageType.APPLICATION_MESSAGE)

        self.assertTrue(first_stream_handler.activated_second_stream.wait(TIMEOUT))

        handler.connection.close().result(TIMEOUT)


class DeadlockStreamHandler(ClientContinuationHandler):
    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.activated_second_stream = Event()

    def on_continuation_message(self, headers, payload, message_type, flags, **kwargs) -> None:
        pass

    def on_continuation_closed(self, **kwargs) -> None:
        print("ACTIVATING")
        self.second_stream.activate(operation="next",
                                    message_type=MessageType.APPLICATION_MESSAGE)
        print("EVENTING")
        self.activated_second_stream.set()
