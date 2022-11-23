"""
WebSocket

All network operations in `awscrt.websocket` are asynchronous.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
import _awscrt
from awscrt import NativeResource
import awscrt.exceptions
from awscrt.http import HttpProxyOptions, HttpRequest
from awscrt.io import ClientBootstrap, TlsConnectionOptions, SocketOptions
from dataclasses import dataclass
from enum import IntEnum
from concurrent.futures import Future
from io import IOBase
import sys
from typing import Callable, Sequence, Tuple


def connect_client(
    *,
    host: str,
    port: int = None,
    handshake_request: HttpRequest,
    bootstrap: ClientBootstrap = None,
    socket_options: SocketOptions = None,
    tls_connection_options: TlsConnectionOptions = None,
    proxy_options: HttpProxyOptions = None,
    # TODO: decide take a bunch of individual callbacks, or a handler class?
    on_connection_setup: Callable[['OnConnectionSetupData'], None],
    on_connection_shutdown: Callable[['OnConnectionShutdownData'], None] = None,
    on_incoming_frame_begin: Callable[['OnIncomingFrameBeginData'], None] = None,
    on_incoming_frame_payload: Callable[['OnIncomingFramePayloadData'], None] = None,
    on_incoming_frame_complete: Callable[['OnIncomingFrameCompleteData'], None] = None,
    enable_read_backpressure: bool = False,
    initial_read_window: int = None,
):
    """Asynchronously establish a client WebSocket connection.

    The `on_connection_setup` callback is invoked once the connection
    has succeeded or failed.

    If successful, a :class:`WebSocket` will be provided in the
    :class:`OnConnectionSetupData`. You should store this WebSocket somewhere,
    so that you can continue using it (the connection will shut down
    if the class is garbage collected).

    The :class:`WebSocket` will shut down after one of these things occur:
        * You call :meth:`WebSocket.close()`
        * You, or the server, sends a CLOSE frame.
        * The underlying socket shuts down.
        * All references to the :class:`WebSocket` are dropped,
          causing it to be garbage collected. However, you should NOT
          rely on this behavior. You should call :meth:`~WebSocket.close()` when you are
          done with a healthy WebSocket, to ensure that shuts down and cleans up.
          It is very easy to accidentally keep a reference around without realizing it.

    Args:
        host: Hostname to connect to.

        port: Port to connect to. If not specified, it defaults to port 443
            when `tls_connection_options` is present, and port 80 otherwise.

        handshake_request: HTTP request for the initial WebSocket handshake.

            The request's method MUST be "GET", and the following headers are
            required::

                Host: <host>
                Upgrade: websocket
                Connection: Upgrade
                Sec-WebSocket-Key: <base64-encoding of 16 random bytes>
                Sec-WebSocket-Version: 13

            You can use :meth:`create_handshake_request()` to make a valid WebSocket
            handshake request, modifying the path and headers to fit your needs,
            and then passing it here.

        bootstrap: Client bootstrap to use when initiating socket connection.
            If not specified, the default singleton is used.

        socket_options: Socket options.
            If not specified, default options are used.

        proxy_options: HTTP Proxy options.
            If not specified, no proxy is used.

        on_connection_setup: Callback invoked when the connect completes.
            Takes a single :class:`OnConnectionSetupData` argument.

            If successful, :attr:`OnConnectionSetupData.websocket` will be set.
            You should store the :class:`WebSocket` somewhere, so you can
            use it to send data when you're ready.
            The other callbacks will be invoked as events occur,
            until the final `on_connection_shutdown` callback.

            If unsuccessful, :attr:`OnConnectionSetupData.exception` will be set,
            and no further callbacks will be invoked.

            If this callback raises an exception, the connection will shut down.

        on_connection_shutdown: Callback invoked when a connection shuts down.
            Takes a single :class:`OnConnectionShutdownData` argument.

            This callback is never invoked if `on_connection_setup` reported an exception.

        on_incoming_frame_begin: Callback invoked once at the start of each incoming frame.
            Takes a single :class:`OnIncomingFrameBeginData` argument.

            Each `on_incoming_frame_begin` call will be followed by 0+
            `on_incoming_frame_payload` calls, followed by one
            `on_incoming_frame_complete` call.

            The "frame complete" callback is guaranteed to be invoked
            once for each "frame begin" callback, even if the connection
            is lost before the whole frame has been received.

            If this callback raises an exception, the connection will shut down.

        on_incoming_frame_payload: Callback invoked 0+ times as payload data arrives.
            Takes a single :class:`OnIncomingFramePayloadData` argument.

            If this callback raises an exception, the connection will shut down.

        on_incoming_frame_complete: Callback invoked when the WebSocket
            is done processing an incoming frame.
            Takes a single :class:`OnIncomingFrameCompleteData` argument.

            If :attr:`OnIncomingFrameCompleteData.exception` is set,
            then something went wrong processing the frame
            or the connection was lost before the frame could be completed.

            If this callback raises an exception, the connection will shut down.
    """
    # TODO: document backpressure
    if enable_read_backpressure:
        if initial_read_window is None:
            raise ValueError("'initial_read_window' must be set if 'enable_read_backpressure' is enabled")
    else:
        initial_read_window = 0xFFFFFFFF  # TODO: fix how this works in C

    if port is None:
        port = 0  # C layer uses zero to indicate "defaults please"

    if bootstrap is None:
        bootstrap = ClientBootstrap.get_or_create_static_default()

    if socket_options is None:
        socket_options = SocketOptions()

    core = _WebSocketCore(
        on_connection_setup,
        on_connection_shutdown,
        on_incoming_frame_begin,
        on_incoming_frame_payload,
        on_incoming_frame_complete)

    _awscrt.websocket_client_connect(
        host,
        port,
        handshake_request,
        bootstrap,
        socket_options,
        tls_connection_options,
        proxy_options,
        enable_read_backpressure,
        initial_read_window,
        core)


def create_handshake_request(*, host: str, path: str = '/') -> HttpRequest:
    """Create an HTTP request with all the required fields for a WebSocket handshake.

    The method will be "GET", and the following headers are added::

        Host: <host>
        Upgrade: websocket
        Connection: Upgrade
        Sec-WebSocket-Key: <base64-encoding of 16 random bytes>
        Sec-WebSocket-Version: 13

    You may can add headers, or modify the path, before using this request.

    Args:
        host: Value for "Host" header
        path: Path (and query) string. Defaults to "/".
    """
    http_request_binding, http_headers_binding = _awscrt.websocket_create_handshake_request(host, path)
    return HttpRequest._from_bindings(http_request_binding, http_headers_binding)


class WebSocket(NativeResource):
    """A WebSocket connection.

    Use :meth:`connect_client()` to establish a new connection.
    """

    def __init__(self, binding):
        # Do not init a WebSocket directly, use connect_client()
        super().__init__()
        self._binding = binding

    def close(self):
        """TODO: implement me"""
        raise NotImplementedError()


class _WebSocketCore(NativeResource):
    # Private class to wrangle callback data from C -> Python.
    # This class is kept alive by C until the final callback occurs.

    def __init__(self,
                 on_connection_setup,
                 on_connection_shutdown,
                 on_incoming_frame_begin,
                 on_incoming_frame_payload,
                 on_incoming_frame_complete):
        self._on_connection_setup_cb = on_connection_setup
        self._on_connection_shutdown_cb = on_connection_shutdown
        self._on_incoming_frame_begin_cb = on_incoming_frame_begin
        self._on_incoming_frame_payload_cb = on_incoming_frame_payload
        self._on_incoming_frame_complete_cb = on_incoming_frame_complete

    def _on_connection_setup(
            self,
            error_code,
            websocket_binding,
            handshake_response_status,
            handshake_response_headers):

        cbdata = OnConnectionSetupData()
        if error_code:
            cbdata.exception = awscrt.exceptions.from_code(error_code)
        else:
            cbdata.websocket = WebSocket(websocket_binding)

        if handshake_response_status != -1:
            cbdata.handshake_response_status = handshake_response_status

        if handshake_response_headers is not None:
            cbdata.handshake_response_headers = handshake_response_headers

        # TODO: get C to pass handshake_response_body

        # Do not let exceptions from the user's callback bubble up any further.
        try:
            self._on_connection_setup_cb(cbdata)
        except Exception:
            print("Exception in WebSocket on_connection_setup callback", file=sys.stderr)
            sys.excepthook(*sys.exc_info())
            if cbdata.websocket:
                cbdata.websocket.close()

    def _on_connection_shutdown(self, error_code):
        pass  # TODO


class Opcode(IntEnum):
    CONTINUATION = 0x0,
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


MAX_PAYLOAD_LENGTH = 0x7FFFFFFFFFFFFFFF


@dataclass
class OnConnectionSetupData:
    """Data passed to the `on_connection_setup` callback"""

    exception: BaseException = None
    """If the connection failed, this exception explains why.

    This is None if the connection succeeded."""

    websocket: 'WebSocket' = None
    """If the connection succeeded, here's the WebSocket.

    You should store this WebSocket somewhere
    (the connection will shut down if the class is garbage collected).

    This is None if the connection failed.
    """

    handshake_response_status: int = None
    """The HTTP response status-code, if you're interested.

    This is present if an HTTP response was received, regardless of whether
    the handshake was accepted or rejected. This always has the value 101
    for successful connections.

    This is None if the connection failed before receiving an HTTP response.
    """

    handshake_response_headers: Sequence[Tuple[str, str]] = None
    """The HTTP response headers, if you're interested.

    These are present if an HTTP response was received, regardless of whether
    the handshake was accepted or rejected.

    This is None if the connection failed before receiving an HTTP response.
    """

    handshake_response_body: bytes = None
    """The HTTP response body, if you're interested.

    This is only present if the server sent a full HTTP response rejecting the handshake.
    It is not present if the connection succeeded,
    or the connection failed for other reasons.
    """


@dataclass
class OnConnectionShutdownData:
    # TODO: document me
    exception: BaseException = None


@dataclass
class IncomingFrame:
    # TODO: document me
    opcode: Opcode
    fin: bool
    rsv1: bool
    rsv2: bool
    rsv3: bool
    payload_length: int


@dataclass
class OnIncomingFrameBeginData:
    # TODO: document me
    frame: IncomingFrame


@dataclass
class OnIncomingFramePayloadData:
    # TODO: document me
    frame: IncomingFrame
    data: bytes


@dataclass
class OnIncomingFrameCompleteData:
    """TODO: document me"""

    frame: IncomingFrame
    """TODO: document me"""

    exception: BaseException = None
    """TODO: document me"""


@dataclass
class OnSendFrameCompleteData:
    exception: BaseException = None
