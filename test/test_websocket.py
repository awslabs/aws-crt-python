# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import asyncio
from awscrt.io import *
from awscrt.websocket import *
from concurrent.futures import Future
from contextlib import closing
import gc
from io import StringIO
import logging
from os import urandom
from queue import Empty, Queue
import secrets
import socket
from test import NativeResourceTest
import threading
from time import sleep, time
from typing import Optional

# using a 3rdparty websocket library for the server
import websockets.server as websockets_server_3rdparty

TIMEOUT = 10.0  # seconds

# uncomment this for logging from the 3rdparty websockets server
# logging.basicConfig(format="%(message)s", level=logging.DEBUG)

# uncomment this for logging from our websockets client
# init_logging(LogLevel.Trace, 'stderr')


@dataclass
class RecvFrame:
    frame: IncomingFrame
    payload: bytes
    exception: Optional[Exception]


class ClientHandler:
    def __init__(self):
        self.websocket = None
        self.setup_future = Future()
        self.shutdown_future = Future()
        self.complete_frames = Queue()
        self.incoming_frame = None
        self.incoming_frame_payload = bytearray()
        self.exception = None

    def connect_sync(self, host, port, **connect_kwargs):
        connect(host=host,
                port=port,
                handshake_request=create_handshake_request(host=host),
                on_connection_setup=self._on_connection_setup,
                on_connection_shutdown=self._on_connection_shutdown,
                on_incoming_frame_begin=self._on_incoming_frame_begin,
                on_incoming_frame_payload=self._on_incoming_frame_payload,
                on_incoming_frame_complete=self._on_incoming_frame_complete,
                **connect_kwargs)
        # wait for on_connection_setup to fire
        setup_data = self.setup_future.result(TIMEOUT)
        assert setup_data.exception is None

    def close_sync(self):
        self.websocket.close()
        # wait for on_connection_shutdown to fire
        self.shutdown_future.result(TIMEOUT)

    def _raise_exception(self, msg=None):
        self.exception = RuntimeError(msg) if msg else RuntimeError()
        raise self.exception

    def _assert(self, condition, msg=None):
        if not condition:
            self._raise_exception(msg)

    def _on_connection_setup(self, data: OnConnectionSetupData):
        self._assert(not self.setup_future.done(), "setup must only fire once")
        self.websocket = data.websocket
        self.setup_future.set_result(data)

    def _on_connection_shutdown(self, data: OnConnectionShutdownData):
        self._assert(self.setup_future.done(), "setup must precede shutdown")
        self._assert(not self.shutdown_future.done(), "shutdown must only fire once")
        self._assert(self.incoming_frame is None, "incoming_frame_complete should fire before shutdown")
        self.shutdown_future.set_result(data)

    def _on_incoming_frame_begin(self, data: OnIncomingFrameBeginData):
        self._assert(self.incoming_frame is None,
                     "incoming_frame_begin cannot fire again until incoming_frame_complete")
        self.incoming_frame = data.frame

    def _on_incoming_frame_payload(self, data: OnIncomingFramePayloadData):
        self._assert(self.incoming_frame == data.frame, "frame from payload callback must match begin callback")
        self.incoming_frame_payload += data.data

    def _on_incoming_frame_complete(self, data: OnIncomingFrameCompleteData):
        self._assert(self.incoming_frame == data.frame,
                     "frame from complete callback must match begin callback")
        self.complete_frames.put(RecvFrame(self.incoming_frame, bytes(self.incoming_frame_payload), data.exception))
        self.incoming_frame = None
        self.incoming_frame_payload.clear()


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

        return self

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
        async with websockets_server_3rdparty.serve(self._run_connection, self._host, self._port, max_size=None) as server:
            # signal that server has started up
            self._server_started_event.set()
            # wait for the signal that we should stop
            await self._server_stop_event.wait()

    async def _run_connection(self, server_connection: websockets_server_3rdparty.WebSocketServerProtocol):
        # this coroutine runs once for each connection to the server
        # when this coroutine exits, the connection gets shut down
        self._current_connection = server_connection
        try:
            # await each message...
            async for msg in server_connection:
                # echo message back
                # print(f"server msg: {msg}")
                await server_connection.send(msg)

        except Exception:
            # an exception is raised when the connection ends,
            # even if the connection ends cleanly, so just swallow it
            pass

        finally:
            self._current_connection = None

    def send_async(self, msg):
        asyncio.run_coroutine_threadsafe(self._current_connection.send(msg), self._server_loop)


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
            # a successful handshake response has no body
            self.assertIsNone(setup_data.handshake_response_body)

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
        self.assertIsNone(setup_data.handshake_response_body)

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
            self.assertIsNotNone(setup_data.handshake_response_body)
            # check that body is a valid string
            self.assertGreater(len(setup_data.handshake_response_body.decode()), 0)

    def test_exception_in_setup_callback_closes_websocket(self):
        with WebSocketServer(self.host, self.port) as server:
            setup_future = Future()
            shutdown_future = Future()

            def bad_setup_callback(data: OnConnectionSetupData):
                setup_future.set_result(data)
                raise RuntimeError("Purposefully raising exception")

            connect(
                host=self.host,
                port=self.port,
                handshake_request=create_handshake_request(host=self.host),
                on_connection_setup=bad_setup_callback,
                on_connection_shutdown=lambda x: shutdown_future.set_result(x))

            # wait for on_connection_setup to fire (and raise exception)
            setup_data = setup_future.result(TIMEOUT)
            self.assertIsNotNone(setup_data.websocket)

            # wait for websocket to close due to exception
            shutdown_future.result(TIMEOUT)

    def test_exception_in_shutdown_callback_has_no_effect(self):
        with WebSocketServer(self.host, self.port) as server:
            setup_future = Future()
            shutdown_future = Future()

            def bad_shutdown_callback(data: OnConnectionShutdownData):
                shutdown_future.set_result(data)
                raise RuntimeError("Purposefully raising exception")

            connect(
                host=self.host,
                port=self.port,
                handshake_request=create_handshake_request(host=self.host),
                on_connection_setup=lambda x: setup_future.set_result(x),
                on_connection_shutdown=bad_shutdown_callback)

            # wait for on_connection_setup to fire
            websocket = setup_future.result(TIMEOUT).websocket

            # close websocket, on_connection_shutdown will fire and raise exception,
            # which should have no effect
            websocket.close()
            shutdown_future.result(TIMEOUT)

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
            self.assertFalse(shutdown_future.done())

            # ...before shutdown has started!
            websocket.close()
            websocket.close()

            # ...while shutdown is happening!
            sleep(0.0000001)
            websocket.close()
            websocket.close()

            # wait for shutdown.
            shutdown_data: OnConnectionShutdownData = shutdown_future.result(TIMEOUT)
            self.assertIsNone(shutdown_data.exception, "Shutdown should have been clean")

            # ...and after shutdown has already occurred!
            websocket.close()
            websocket.close()

    def _send_and_receive(self, handler, opcode, payload):
        send_complete_future = Future()

        handler.websocket.send_frame(opcode, payload, on_complete=lambda x: send_complete_future.set_result(x))

        # wait for send_frame operation to complete
        send_complete_data: OnSendFrameCompleteData = send_complete_future.result(TIMEOUT)
        self.assertIsNone(send_complete_data.exception)

        # wait to receive echo message back
        recv: RecvFrame = handler.complete_frames.get(timeout=TIMEOUT)
        # assert that expected types are received (`is True` vs checking that it evaluates to True)
        self.assertIsInstance(recv.frame.opcode, Opcode)
        self.assertEqual(recv.frame.opcode, opcode)
        self.assertIs(recv.frame.fin, True)

        # check that the received payload matches what we sent in
        if isinstance(payload, str):
            self.assertEqual(recv.payload, payload.encode('utf-8'))
        elif payload is None:
            self.assertEqual(recv.payload, b'')
        else:
            self.assertEqual(recv.payload, payload)

        self.assertIsNone(handler.exception)

    def test_send_receive_data(self):
        # test sending and receiving TEXT and BINARY frames
        # (the server echos these types of messages back)
        with WebSocketServer(self.host, self.port) as server:
            handler = ClientHandler()
            handler.connect_sync(self.host, self.port)

            # try sending all kinds of "buffer protocol" types
            self._send_and_receive(handler, Opcode.TEXT, "str with ascii")
            self._send_and_receive(handler, Opcode.TEXT, "str with unicode --> 👁👄👁 <--")
            self._send_and_receive(handler, Opcode.TEXT, "str with embedded null byte --> \0 <--")
            self._send_and_receive(handler, Opcode.TEXT, b"bytes of text")
            self._send_and_receive(handler, Opcode.TEXT, bytearray(b"bytearray of text"))
            self._send_and_receive(handler, Opcode.TEXT, memoryview(b"memoryview of text"))
            self._send_and_receive(handler, Opcode.TEXT, memoryview(b"...memoryview slice...")[3: -3])
            self._send_and_receive(handler, Opcode.TEXT, "")  # empty
            self._send_and_receive(handler, Opcode.TEXT, None)

            # try sending all kinds of "buffer protocol" types
            self._send_and_receive(handler, Opcode.BINARY, "str sent binary")
            self._send_and_receive(handler, Opcode.BINARY, b"bytes sent binary")
            self._send_and_receive(handler, Opcode.BINARY, bytearray(b"bytearray sent binary"))
            self._send_and_receive(handler, Opcode.BINARY, memoryview(b"memoryview sent binary"))
            self._send_and_receive(handler, Opcode.BINARY, memoryview(b"...memoryview slice sent binary...")[3: -3])
            self._send_and_receive(handler, Opcode.BINARY, bytes())  # empty
            self._send_and_receive(handler, Opcode.BINARY, None)

            # send something very big
            self._send_and_receive(handler, Opcode.BINARY, urandom(1024 * 1024 * 4))

            handler.close_sync()
            self.assertIsNone(handler.exception)

    def test_send_frame_exceptions(self):
        with WebSocketServer(self.host, self.port) as server:
            handler = ClientHandler()
            handler.connect_sync(self.host, self.port)

            # we don't currently support sending streams
            with self.assertRaises(TypeError):
                handler.websocket.send_frame(Opcode.TEXT, StringIO("text stream"))

            # raising an exception from the completion-callback should result in websocket closing
            def bad_completion_callback(data):
                raise RuntimeError("Purposefully raising exception")

            handler.websocket.send_frame(Opcode.TEXT, "asdf", on_complete=bad_completion_callback)

            # wait for shutdown...
            handler.shutdown_future.result(TIMEOUT)

            # shouldn't be able to send frame after websocket closes
            with self.assertRaises(Exception) as raises:
                handler.websocket.send_frame(Opcode.TEXT, "asdf")
            self.assertIn("AWS_ERROR_HTTP_WEBSOCKET_CLOSE_FRAME_SENT", str(raises.exception))

            self.assertIsNone(handler.exception)

    def test_exception_from_incoming_frame_callback_closes_websocket(self):
        # loop 3 times, once for each type of on_incoming_frame_X callback
        for i in ('begin', 'payload', 'complete'):
            with WebSocketServer(self.host, self.port) as server:
                setup_future = Future()
                shutdown_future = Future()

                def bad_incoming_frame_callback(data):
                    raise RuntimeError("Purposefully raising exception")

                connect(
                    host=self.host,
                    port=self.port,
                    handshake_request=create_handshake_request(host=self.host),
                    on_connection_setup=lambda x: setup_future.set_result(x),
                    on_connection_shutdown=lambda x: shutdown_future.set_result(x),
                    on_incoming_frame_begin=bad_incoming_frame_callback if i == 'begin' else None,
                    on_incoming_frame_payload=bad_incoming_frame_callback if i == 'payload' else None,
                    on_incoming_frame_complete=bad_incoming_frame_callback if i == 'complete' else None,
                )

                # wait for on_connection_setup to fire
                websocket = setup_future.result(TIMEOUT).websocket

                # send a frame that the server will echo back
                websocket.send_frame(Opcode.TEXT, "echo")

                # wait for the frame to echo back, firing the bad callback,
                # which raises an exception, which should result in the WebSocket closing
                shutdown_future.result(TIMEOUT)

    def test_manage_read_window(self):
        # test that users can manage how much data is read by managing the read window
        with WebSocketServer(self.host, self.port) as server:
            handler = ClientHandler()
            handler.connect_sync(self.host, self.port, manage_read_window=True, initial_read_window=1000)

            # client's read window is 1000-bytes
            # have the server send 10 messages with 100-byte payloads
            # they should all get through

            for i in range(10):
                msg = secrets.token_bytes(100)  # random msg for server to send
                server.send_async(msg)
                recv: RecvFrame = handler.complete_frames.get(timeout=TIMEOUT)
                self.assertEqual(recv.payload, msg, "did not receive expected payload")

            # client window is now 0
            # have server send a 1000 byte message, NONE of its payload should arrive

            msg = secrets.token_bytes(1000)  # random msg for server to send
            server.send_async(msg)
            with self.assertRaises(Empty):
                handler.complete_frames.get(timeout=1.0)
            self.assertEqual(len(handler.incoming_frame_payload), 0, "No payload should arrive while window is 0")

            # now increment client's window to 500
            # half (500/1000) the bytes should flow in

            handler.websocket.increment_read_window(500)
            max_wait_until = time() + TIMEOUT
            while len(handler.incoming_frame_payload) < 500:
                sleep(0.001)
                self.assertLess(time(), max_wait_until, "timed out waiting for all bytes")
            sleep(1.0)  # sleep a moment to be sure we don't receive MORE than 500 bytes
            self.assertEqual(len(handler.incoming_frame_payload), 500, "received more bytes than expected")

            # client's window is 0 again, 500 bytes are still waiting to flow in
            # increment the window to let the rest in
            # let's do it by calling increment a bunch of times in a row, just to be different

            handler.websocket.increment_read_window(100)
            handler.websocket.increment_read_window(100)
            handler.websocket.increment_read_window(100)
            handler.websocket.increment_read_window(100)
            handler.websocket.increment_read_window(100)

            recv: RecvFrame = handler.complete_frames.get(timeout=TIMEOUT)
            self.assertEqual(recv.payload, msg, "did not receive expected payload")

            # done!
            handler.close_sync()
