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
from typing import Callable, Sequence, Tuple


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
    exception: BaseException = None
    websocket: 'WebSocket' = None
    handshake_response_status: int = None
    handshake_response_headers: Sequence[Tuple[str, str]] = None
    handshake_response_body: bytes = None


@dataclass
class OnConnectionShutdownData:
    exception: BaseException = None


@dataclass
class IncomingFrame:
    opcode: Opcode
    fin: bool
    rsv1: bool
    rsv2: bool
    rsv3: bool
    payload_length: int


@dataclass
class OnIncomingFrameBeginData:
    frame: IncomingFrame


@dataclass
class OnIncomingFramePayloadData:
    frame: IncomingFrame
    data: bytes


@dataclass
class OnIncomingFrameCompleteData:
    frame: IncomingFrame
    exception: BaseException = None


@dataclass
class OnSendFrameCompleteData:
    exception: BaseException = None


class WebSocket(NativeResource):

    @classmethod
    def connect_client(
        cls, *,
        host: str,
        port: int = None,
        handshake_request: HttpRequest,
        bootstrap: ClientBootstrap = None,
        socket_options: SocketOptions = None,
        tls_connection_options: TlsConnectionOptions = None,
        proxy_options: HttpProxyOptions = None,
        # TODO: decide take a bunch of individual callbacks, or a handler class?
        on_connection_setup: Callable[[OnConnectionSetupData], None],
        on_connection_shutdown: Callable[[OnConnectionShutdownData], None] = None,
        on_incoming_frame_begin: Callable[[OnIncomingFrameBeginData], None] = None,
        on_incoming_frame_payload: Callable[[OnIncomingFramePayloadData], None] = None,
        on_incoming_frame_complete: Callable[[OnIncomingFrameCompleteData], None] = None,
        enable_read_backpressure: bool = False,
        initial_read_window: int = None,
    ):

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

        core = _WebSocketCore(on_connection_setup, on_connection_shutdown,
                              on_incoming_frame_begin, on_incoming_frame_payload,
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

    def __init__(self, binding):
        super().__init__()
        self._binding = binding

    def close(self, graceful_shutdown=True):
        raise NotImplementedError()

    def send_frame(
        self, *,
        opcode: Opcode,
        fin: bool = True,
        rsv1: bool = False,
        rsv2: bool = False,
        rsv3: bool = False,
        # TODO: decide 3 different args for payload types? or single arg and try to detect type?
        payload_bytes: bytes = None,
        payload_str: str = None,
        payload_stream: IOBase = None,
        payload_length: int = None,
        # TODO: decide completion callback? future? both?
        on_complete: Callable[[OnSendFrameCompleteData], None] = None,
    ) -> Future:
        raise NotImplementedError()

    def increment_read_window(self, more_bytes):
        raise NotImplementedError()


def create_handshake_request(host: str, path: str) -> HttpRequest:
    raise NotImplementedError()


class _WebSocketCore(NativeResource):
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

        self._on_connection_setup_cb(cbdata)
