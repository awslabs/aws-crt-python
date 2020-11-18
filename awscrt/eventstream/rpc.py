"""
event-stream RPC (remote procedure call) protocol library for `awscrt`.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from abc import ABC, abstractmethod
from awscrt import NativeResource
import awscrt.exceptions
from awscrt.eventstream import Header
from awscrt.io import ClientBootstrap, SocketOptions, TlsConnectionOptions
from collections.abc import ByteString, Callable
from concurrent.futures import Future
from enum import IntEnum
from functools import partial
from typing import Optional, Sequence
import weakref

__all__ = [
    'MessageType',
    'MessageFlag',
    'ClientConnectionHandler',
    'ClientConnection',
    'ClientContinuation',
    'ClientContinuationHandler',
]


class MessageType(IntEnum):
    """Types of messages in the event-stream RPC protocol.

    The APPLICATION_MESSAGE and APPLICATION_ERROR types may only be sent
    on streams, and will never arrive as a protocol message (stream-id 0).

    For all other message types, they may only be sent as protocol messages
    (stream-id 0), and will never arrive as a stream message.

    Different message types expect specific headers and flags, consult documentation."""

    APPLICATION_MESSAGE = 0
    """Application message"""

    APPLICATION_ERROR = 1
    """Application error"""

    PING = 2
    """Ping"""

    PING_RESPONSE = 3
    """Ping response"""

    CONNECT = 4
    """Connect"""

    CONNECT_ACK = 5
    """Connect acknowledgement

    If the CONNECTION_ACCEPTED flag is not present, the connection has been rejected."""

    PROTOCOL_ERROR = 6
    """Protocol error"""

    INTERNAL_ERROR = 7
    """Internal error"""

    def __format__(self, format_spec):
        # override so formatted string doesn't simply look like an int
        return str(self)


class MessageFlag:
    """Flags for messages in the event-stream RPC protocol.

    Flags may be XORed together.
    Not all flags can be used with all message types, consult documentation.
    """
    # TODO: when python 3.5 is dropped this class should inherit from IntFlag.
    # When doing this, be sure to update type-hints and callbacks to pass
    # MessageFlag instead of plain int.

    NONE = 0
    """No flags"""

    CONNECTION_ACCEPTED = 0x1
    """Connection accepted

    If this flag is absent from a CONNECT_ACK, the connection has been rejected."""

    TERMINATE_STREAM = 0x2
    """Terminate stream

    This message may be used with any message type.
    The sender will close their connection after the message is written to the wire.
    The receiver will close their connection after delivering the message to the user."""

    def __format__(self, format_spec):
        # override so formatted string doesn't simply look like an int
        return str(self)


class ClientConnectionHandler(ABC):
    """Base class for handling connection events.

    Inherit from this class and override methods to handle connection events.
    All callbacks for this connection will be invoked on the same thread,
    and `on_connection_setup()` will always be the first callback invoked.

    Note that if the handler is garbage-collected, its callbacks will
    not be invoked. To receive all events, maintain a reference to the
    handler until its connection shuts down (or fails setup).
    """

    @abstractmethod
    def on_connection_setup(self, connection, error, **kwargs) -> None:
        """Invoked upon completion of the setup attempt.

        If setup was successful, the connection is provided to the user.
        The user must keep a reference to the connection or it will be
        garbage-collected and closed. A common pattern is to store a
        reference to the connection in the handler. Example:
        ```
            def on_connection_setup(self, connection, error, **kwargs):
                if error:
                    ... do error handling ...
                else:
                    self.connection = connection
        ```
        Setup will always be the first callback invoked on the handler.
        If setup failed, no further callbacks will be invoked on this handler.

        Args:
            connection: The connection, if setup was successful,
                or None if setup failed.

            error: None, if setup was successful, or an Exception
                if setup failed.

            `**kwargs`: Forward compatibility kwargs.
        """
        pass

    @abstractmethod
    def on_connection_shutdown(self, reason: Optional[Exception], **kwargs) -> None:
        """Invoked when the connection finishes shutting down.

        This event will not be invoked if connection setup failed.

        Note that this event will not be invoked if the handler is
        garbage-collected before the shutdown process completes.

        Args:
            reason: Reason will be None if the user initiated the shutdown,
                otherwise the reason will be an Exception.

            **kwargs: Forward compatibility kwargs.
        """
        pass

    @abstractmethod
    def on_protocol_message(
            self,
            headers: Sequence[Header],
            payload: bytes,
            message_type: MessageType,
            flags: int,
            **kwargs) -> None:
        """Invoked when a message for the connection (stream-id 0) is received.

        Args:
            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from MessageFlag may be
                XORed together. Not all flags can be used with all message
                types, consult documentation.

            **kwargs: Forward compatibility kwargs.
        """

        pass


def _to_binding_msg_args(headers, payload, message_type, flags):
    """
    Transform args that a python send-msg function would take,
    into args that a native send-msg function would take.
    """
    # python functions for sending messages
    if headers is None:
        headers = []
    else:
        headers = [i._as_binding_tuple() for i in headers]
    if payload is None:
        payload = b''
    if flags is None:
        flags = MessageFlag.NONE
    return (headers, payload, message_type, flags)


def _from_binding_msg_args(headers, payload, message_type, flags):
    """
    Transform msg-received args that came from native,
    into msg-received args presented to python users.
    """
    headers = [Header._from_binding_tuple(i) for i in headers]
    if payload is None:
        payload = b''
    message_type = MessageType(message_type)
    return (headers, payload, message_type, flags)


class ClientConnection(NativeResource):
    """A client connection for the event-stream RPC protocol.

    Use :meth:`ClientConnection.connect()` to establish a new
    connection.

    Attributes:
        host_name (str): Remote host name.

        port (int): Remote port.

        shutdown_future (concurrent.futures.Future[None]): Completes when this
            connection has finished shutting down. Future will contain a
            result of None, or an exception indicating why shutdown occurred.
            Note that the connection may have been garbage-collected before
            this future completes.
    """

    __slots__ = ['host_name', 'port', 'shutdown_future']

    def __init__(self, host_name, port):
        # Do no instantiate directly, use static connect method
        super().__init__()
        self.host_name = host_name  # type: str
        self.port = port  # type: int
        self.shutdown_future = Future()  # type: Future

    @classmethod
    def connect(
            cls,
            *,
            handler: ClientConnectionHandler,
            host_name: str,
            port: int,
            bootstrap: ClientBootstrap,
            socket_options: Optional[SocketOptions] = None,
            tls_connection_options: Optional[TlsConnectionOptions] = None) -> Future:
        """Asynchronously establish a new ClientConnection.

        Args:
            handler: Handler for connection events.

            host_name: Connect to host.

            port: Connect to port.

            bootstrap: Client bootstrap to use when initiating socket connection.

            socket_options: Optional socket options.
                If None is provided, then default options are used.

            tls_connection_options: Optional TLS
                connection options. If None is provided, then the connection will
                be attempted over plain-text.

        Returns:
            concurrent.futures.Future: A Future which completes when the connection succeeds or fails.
            If successful, the Future will contain None.
            Otherwise it will contain an exception.
            If the connection is successful, it will be made available via
            the handler's on_connection_setup callback.
        """

        if not socket_options:
            socket_options = SocketOptions()

        future = Future()

        # Connection is not made available to user until setup callback fires
        connection = cls(host_name, port)

        # We must be careful to avoid circular references that prevent the connection from getting GC'd.
        # Only the internal _on_setup callback binds strong references to the connection and handler.
        # This is ok because it fires exactly once, and references to it are cleared afterwards.
        # All other callbacks must bind weak references to the handler,
        # or references to futures within the connection rather than the connection itself.
        handler_weakref = weakref.ref(handler)

        _awscrt.event_stream_rpc_client_connection_connect(
            host_name,
            port,
            bootstrap,
            socket_options,
            tls_connection_options,
            partial(cls._on_connection_setup, future, handler, connection),
            partial(cls._on_connection_shutdown, connection.shutdown_future, handler_weakref),
            partial(cls._on_protocol_message, handler_weakref))

        return future

    @staticmethod
    def _on_connection_setup(bound_future, bound_handler, bound_connection, binding, error_code):
        if error_code:
            connection = None
            error = awscrt.exceptions.from_code(error_code)
        else:
            connection = bound_connection
            connection._binding = binding
            error = None

        try:
            bound_handler.on_connection_setup(connection=connection, error=error)
        finally:
            # ensure future completes, even if user callback had unhandled exception
            if error:
                bound_future.set_exception(error)
            else:
                bound_future.set_result(None)

    @staticmethod
    def _on_connection_shutdown(bound_future, bound_weak_handler, error_code):
        reason = awscrt.exceptions.from_code(error_code) if error_code else None
        try:
            handler = bound_weak_handler()
            if handler:
                handler.on_connection_shutdown(reason=reason)
        finally:
            # ensure future completes, even if user callback had unhandled exception
            if reason:
                bound_future.set_exception(reason)
            else:
                bound_future.set_result(None)

    @staticmethod
    def _on_continuation_closed(bound_future, bound_weak_handler):
        try:
            handler = bound_weak_handler()
            if handler:
                handler.on_continuation_closed()
        finally:
            # ensure future completes, even if user callback had unhandled exception
            bound_future.set_result(None)

    @staticmethod
    def _on_protocol_message(bound_weak_handler, headers, payload, message_type, flags):
        handler = bound_weak_handler()
        if handler:
            # transform from simple types to actual classes
            headers, payload, message_type, flags = _from_binding_msg_args(headers, payload, message_type, flags)
            handler.on_protocol_message(
                headers=headers,
                payload=payload,
                message_type=message_type,
                flags=flags)

    @staticmethod
    def _on_continuation_message(bound_weak_handler, headers, payload, message_type, flags):
        handler = bound_weak_handler()
        if handler:
            # transform from simple types to actual classes
            headers, payload, message_type, flags = _from_binding_msg_args(headers, payload, message_type, flags)
            handler.on_continuation_message(
                headers=headers,
                payload=payload,
                message_type=message_type,
                flags=flags)

    @staticmethod
    def _on_flush(bound_future, bound_callback, error_code):
        # invoked when a message is flushed (written to wire), or canceled due to connection error.
        e = awscrt.exceptions.from_code(error_code) if error_code else None
        try:
            if bound_callback:
                bound_callback(error=e)
        finally:
            # ensure future completes, even if user callback had unhandled exception
            if error_code:
                bound_future.set_exception(e)
            else:
                bound_future.set_result(None)

    def close(self):
        """Close the connection.

        Shutdown is asynchronous. This call has no effect if the connection is already
        closing.

        Returns:
            concurrent.futures.Future: This connection's :attr:`shutdown_future`,
            which completes when shutdown has finished.
        """
        # TODO: let user pass their own exception/error-code/reason for closing
        _awscrt.event_stream_rpc_client_connection_close(self._binding)
        return self.shutdown_future

    def is_open(self):
        """
        Returns:
            bool: True if this connection is open and usable, False otherwise.
            Check :attr:`shutdown_future` to know when the connection is completely
            finished shutting down.
        """
        return _awscrt.event_stream_rpc_client_connection_is_open(self._binding)

    def send_protocol_message(
            self,
            *,
            headers: Optional[Sequence[Header]] = None,
            payload: Optional[ByteString] = None,
            message_type: MessageType,
            flags: Optional[int] = None,
            on_flush: Callable = None) -> Future:
        """Send a protocol message.

        Protocol messages use stream-id 0.

        Use the returned future, or the `on_flush` callback, to be informed
        when the message is successfully written to the wire, or fails to send.

        Keyword Args:
            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from MessageFlag may be
                XORed together. Not all flags can be used with all message
                types, consult documentation.

            on_flush: Callback invoked when the message is successfully written
                to the wire, or fails to send. The function should take the
                following arguments and return nothing:

                *   `error` (Optional[Exception]): None if the message was
                    successfully written to the wire, or an Exception
                    if it failed to send.

                *   `**kwargs` (dict): Forward compatibility kwargs.

                This callback is always invoked on the connection's event-loop
                thread.

        Returns:
            A future which completes with a result of None if the
            message is successfully written to the wire,
            or an exception if the message fails to send.
        """
        future = Future()

        # native code deals with simplified types
        headers, payload, message_type, flags = _to_binding_msg_args(headers, payload, message_type, flags)

        _awscrt.event_stream_rpc_client_connection_send_protocol_message(
            self._binding,
            headers,
            payload,
            message_type,
            flags,
            partial(self._on_flush, future, on_flush))
        return future

    def new_stream(self, handler: 'ClientContinuationHandler') -> 'ClientContinuation':
        """
        Create a new stream.

        The stream will send no data until :meth:`ClientContinuation.activate()`
        is called. Call activate() when you're ready for callbacks and events to fire.

        Args:
            handler: Handler to process continuation messages and state changes.

        Returns:
            The new continuation object.
        """
        handler_weakref = weakref.ref(handler)
        closed_future = Future()
        binding = _awscrt.event_stream_rpc_client_connection_new_stream(
            self,
            partial(self._on_continuation_message, handler_weakref),
            partial(self._on_continuation_closed, closed_future, handler_weakref))
        return ClientContinuation(binding, closed_future, self)


class ClientContinuation(NativeResource):
    """
    A continuation of messages on a given stream-id.

    Create with :meth:`ClientConnection.new_stream()`.

    The stream will send no data until :meth:`ClientContinuation.activate()`
    is called. Call activate() when you're ready for callbacks and events to fire.

    Attributes:
        connection (ClientConnection): This stream's connection.

        closed_future (Future) : Future which completes with a result of None
            when the continuation has closed.
    """

    def __init__(self, binding, closed_future, connection):
        # Do not instantiate directly, use ClientConnection.new_stream()
        super().__init__()
        self._binding = binding
        self.connection = connection  # type: ClientConnection
        self.closed_future = closed_future  # type: Future

    def activate(
            self,
            *,
            operation: str,
            headers: Sequence[Header] = None,
            payload: ByteString = None,
            message_type: MessageType,
            flags: int = None,
            on_flush: Callable = None):
        """
        Activate the stream by sending its first message.

        Use the returned future, or the `on_flush` callback, to be informed
        when the message is successfully written to the wire, or fails to send.

        activate() may only be called once, use send_message() to write further
        messages on this stream-id.

        Keyword Args:
            operation: Operation name for this stream.

            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from MessageFlag may be
                XORed together. Not all flags can be used with all message
                types, consult documentation.

            on_flush: Callback invoked when the message is successfully written
                to the wire, or fails to send. The function should take the
                following arguments and return nothing:

                *   `error` (Optional[Exception]): None if the message was
                    successfully written to the wire, or an Exception
                    if it failed to send.

                *   `**kwargs` (dict): Forward compatibility kwargs.

                This callback is always invoked on the connection's event-loop
                thread.

        Returns:
            A future which completes with a result of None if the
            message is successfully written to the wire,
            or an exception if the message fails to send.
        """

        flush_future = Future()

        # native code deals with simplified types
        headers, payload, message_type, flags = _to_binding_msg_args(headers, payload, message_type, flags)

        _awscrt.event_stream_rpc_client_continuation_activate(
            self._binding,
            operation,
            headers,
            payload,
            message_type,
            flags,
            partial(ClientConnection._on_flush, flush_future, on_flush))

        return flush_future

    def send_message(
            self,
            *,
            headers: Sequence[Header] = None,
            payload: ByteString = None,
            message_type: MessageType,
            flags: int = None,
            on_flush: Callable = None) -> Future:
        """
        Send a continuation message.

        Use the returned future, or the `on_flush` callback, to be informed
        when the message is successfully written to the wire, or fails to send.

        Note that the the first message on a stream-id must be sent with activate(),
        send_message() is for all messages that follow.

        Keyword Args:
            operation: Operation name for this stream.

            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from MessageFlag may be
                XORed together. Not all flags can be used with all message
                types, consult documentation.

            on_flush: Callback invoked when the message is successfully written
                to the wire, or fails to send. The function should take the
                following arguments and return nothing:

                *   `error` (Optional[Exception]): None if the message was
                    successfully written to the wire, or an Exception
                    if it failed to send.

                *   `**kwargs` (dict): Forward compatibility kwargs.

                This callback is always invoked on the connection's event-loop
                thread.

        Returns:
            A future which completes with a result of None if the
            message is successfully written to the wire,
            or an exception if the message fails to send.
        """
        future = Future()
        # native code deals with simplified types
        headers, payload, message_type, flags = _to_binding_msg_args(headers, payload, message_type, flags)

        _awscrt.event_stream_rpc_client_continuation_send_message(
            self._binding,
            headers,
            payload,
            message_type,
            flags,
            partial(ClientConnection._on_flush, future, on_flush))
        return future

    def is_closed(self):
        return _awscrt.event_stream_rpc_client_continuation_is_closed(self._binding)


class ClientContinuationHandler(ABC):
    """Base class for handling stream continuation events.

    Inherit from this class and override methods to handle events.
    All callbacks will be invoked on the same thread (the same thread used by
    the connection).

    A common pattern is to store the continuation within its handler. Ex:
    `continuation_handler.continuation = connection.new_stream(continuation_handler)`

    Note that if the handler is garbage-collected, its callbacks will no
    longer be invoked. Maintain a reference to the handler until the
    continuation is closed to receive all events.
    """

    @abstractmethod
    def on_continuation_message(
            self,
            headers: Sequence[Header],
            payload: bytes,
            message_type: MessageType,
            flags: int,
            **kwargs) -> None:
        """Invoked when a message is received on this continuation.

        Args:
            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from MessageFlag may be
                XORed together. Not all flags can be used with all message
                types, consult documentation.

            **kwargs: Forward compatibility kwargs.
        """
        pass

    @abstractmethod
    def on_continuation_closed(self, **kwargs) -> None:
        """Invoked when the continuation is closed.

        Once the continuation is closed, no more messages may be sent or received.
        The continuation is closed when a message is sent or received with
        the TERMINATE_STREAM flag, or when the connection shuts down.

        Note that this event will not be invoked if the handler is
        garbage-collected before the stream completes.

        Args:
            **kwargs: Forward compatibility kwargs.
        """
        pass
