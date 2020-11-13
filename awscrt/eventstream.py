"""
event-stream library for `awscrt`.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from abc import ABC, abstractmethod
from awscrt import NativeResource
import awscrt.exceptions
from awscrt.io import ClientBootstrap, SocketOptions, TlsConnectionOptions
from collections.abc import ByteString, Callable
from concurrent.futures import Future
from enum import IntEnum
from functools import partial
from typing import Any, Optional, Sequence
from uuid import UUID
import weakref


_BYTE_MIN = -2**7
_BYTE_MAX = 2**7 - 1
_INT16_MIN = -2**15
_INT16_MAX = 2**15 - 1
_INT32_MIN = -2**31
_INT32_MAX = 2**31 - 1
_INT64_MIN = -2**63
_INT64_MAX = 2**63 - 1


class EventStreamHeaderType(IntEnum):
    """Supported types for the value within an EventStreamHeader"""

    BOOL_TRUE = 0
    """Value is True.

    No actual value is transmitted on the wire."""

    BOOL_FALSE = 1
    """Value is False.

    No actual value is transmitted on the wire."""

    BYTE = 2
    """Value is signed 8-bit int."""

    INT16 = 3
    """Value is signed 16-bit int."""

    INT32 = 4
    """Value is signed 32-bit int."""

    INT64 = 5
    """Value is signed 64-bit int."""

    BYTE_BUF = 6
    """Value is raw bytes."""

    STRING = 7
    """Value is a str.

    Transmitted on the wire as utf-8"""

    TIMESTAMP = 8
    """Value is a posix timestamp (seconds since Unix epoch).

    Transmitted on the wire as a 64-bit int"""

    UUID = 9
    """Value is a UUID.

    Transmitted on the wire as 16 bytes"""

    def __format__(self, format_spec):
        # override so formatted string doesn't simply look like an int
        return str(self)


class EventStreamHeader:
    """A header in an event-stream message.

    Each header has a name, value, and type.
    :class:`EventStreamHeaderType` enumerates the supported value types.

    Create a header with one of the EventStreamHeader.from_X() functions.
    """

    def __init__(self, name: str, value: Any, header_type: EventStreamHeaderType):
        # do not call directly, use EventStreamHeader.from_xyz() methods.
        self._name = name
        self._value = value
        self._type = header_type

    @classmethod
    def from_bool(cls, name: str, value: bool) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type BOOL_TRUE or BOOL_FALSE"""
        if value:
            return cls(name, True, EventStreamHeaderType.BOOL_TRUE)
        else:
            return cls(name, False, EventStreamHeaderType.BOOL_FALSE)

    @classmethod
    def from_byte(cls, name: str, value: int) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type BYTE

        The value must fit in an 8-bit signed int"""
        value = int(value)
        if value < _BYTE_MIN or value > _BYTE_MAX:
            raise ValueError("Value {} cannot fit in signed 8-bit byte".format(value))
        return cls(name, value, EventStreamHeaderType.BYTE)

    @classmethod
    def from_int16(cls, name: str, value: int) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type INT16

        The value must fit in an 16-bit signed int"""
        value = int(value)
        if value < _INT16_MIN or value > _INT16_MAX:
            raise ValueError("Value {} cannot fit in signed 16-bit int".format(value))
        return cls(name, value, EventStreamHeaderType.INT16)

    @classmethod
    def from_int32(cls, name: str, value: int) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type INT32

        The value must fit in an 32-bit signed int"""
        value = int(value)
        if value < _INT32_MIN or value > _INT32_MAX:
            raise ValueError("Value {} cannot fit in signed 32-bit int".format(value))
        return cls(name, value, EventStreamHeaderType.INT32)

    @classmethod
    def from_int64(cls, name: str, value: int) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type INT64

        The value must fit in an 64-bit signed int"""
        value = int(value)
        if value < _INT64_MIN or value > _INT64_MAX:
            raise ValueError("Value {} cannot fit in signed 64-bit int".format(value))
        return cls(name, value, EventStreamHeaderType.INT64)

    @classmethod
    def from_byte_buf(cls, name: str, value: ByteString) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type BYTES

        The value must be a bytes-like object"""
        return cls(name, value, EventStreamHeaderType.BYTE_BUF)

    @classmethod
    def from_string(cls, name: str, value: str) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type STRING"""
        value = str(value)
        return cls(name, value, EventStreamHeaderType.STRING)

    @classmethod
    def from_timestamp(cls, name: str, value: int) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type TIMESTAMP

        Value must be a posix timestamp (seconds since Unix epoch)"""

        value = int(value)
        if value < _INT64_MIN or value > _INT64_MAX:
            raise ValueError("Value {} exceeds timestamp limits".format(value))
        return cls(name, value, EventStreamHeaderType.TIMESTAMP)

    @classmethod
    def from_uuid(cls, name: str, value: UUID) -> 'EventStreamHeader':
        """Create an EventStreamHeader of type UUID

        The value must be a UUID"""

        if not isinstance(value, UUID):
            raise TypeError("Value must be UUID, not {}".format(type(value)))
        return cls(name, value, EventStreamHeaderType.UUID)

    @classmethod
    def _from_binding_tuple(cls, binding_tuple):
        # native code deals with a simplified tuple, rather than full class
        name, value, header_type = binding_tuple
        header_type = EventStreamHeaderType(header_type)
        if header_type == EventStreamHeaderType.UUID:
            value = UUID(bytes=value)
        return cls(name, value, header_type)

    def _as_binding_tuple(self):
        # native code deals with a simplified tuple, rather than full class
        if self._type == EventStreamHeaderType.UUID:
            value = self._value.bytes
        else:
            value = self._value
        return (self._name, value, self._type)

    @property
    def name(self) -> str:
        """Header name"""
        return self._name

    @property
    def type(self) -> EventStreamHeaderType:
        """Header type"""
        return self._type

    @property
    def value(self) -> Any:
        """Header value

        The header's type determines the value's type.
        Use the value_as_X() methods for type-checked queries."""
        return self._value

    def _value_as(self, header_type: EventStreamHeaderType) -> Any:
        if self._type != header_type:
            raise TypeError("Header type is {}, not {}".format(self._type, header_type))
        return self._value

    def value_as_bool(self) -> bool:
        """Return bool value

        Raises an exception if type is not BOOL_TRUE or BOOL_FALSE"""
        if self._type == EventStreamHeaderType.BOOL_TRUE:
            return True
        if self._type == EventStreamHeaderType.BOOL_FALSE:
            return False
        raise TypeError(
            "Header type is {}, not {} or {}".format(
                self._type,
                EventStreamHeaderType.BOOL_TRUE,
                EventStreamHeaderType.BOOL_FALSE))

    def value_as_byte(self) -> int:
        """Return value of 8-bit signed int

        Raises an exception if type is not INT8"""
        return self._value_as(EventStreamHeaderType.BYTE)

    def value_as_int16(self) -> int:
        """Return value of 16-bit signed int

        Raises an exception if type is not INT16"""
        return self._value_as(EventStreamHeaderType.INT16)

    def value_as_int32(self) -> int:
        """Return value of 32-bit signed int

        Raises an exception if type is not INT32"""
        return self._value_as(EventStreamHeaderType.INT32)

    def value_as_int64(self) -> int:
        """Return value of 64-bit signed int

        Raises an exception if type is not INT64"""
        return self._value_as(EventStreamHeaderType.INT64)

    def value_as_byte_buf(self) -> ByteString:
        """Return value of bytes

        Raises an exception if type is not BYTE_BUF"""
        return self._value_as(EventStreamHeaderType.BYTE_BUF)

    def value_as_string(self) -> str:
        """Return value of string

        Raises an exception if type is not STRING"""
        return self._value_as(EventStreamHeaderType.STRING)

    def value_as_timestamp(self) -> int:
        """Return value of timestamp (seconds since Unix epoch)

        Raises an exception if type is not TIMESTAMP"""
        return self._value_as(EventStreamHeaderType.TIMESTAMP)

    def value_as_uuid(self) -> UUID:
        """Return value of UUID

        Raises an exception if type is not UUID"""
        return self._value_as(EventStreamHeaderType.UUID)

    def __str__(self):
        return "{}: {} <{}>".format(
            self._name,
            repr(self._value),
            self._type.name)

    def __repr__(self):
        return "{}({}, {}, {})".format(
            self.__class__.__name__,
            repr(self._name),
            repr(self._value),
            repr(self._type))


class EventStreamRpcMessageType(IntEnum):
    """Types of event-stream RPC messages.

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


class EventStreamRpcMessageFlag:
    """Flags for event-stream RPC messages.

    Flags may be XORed together.
    Not all flags can be used with all message types, consult documentation.
    """
    # TODO: when python 3.5 is dropped this class should inherit from IntFlag.
    # When doing this, be sure to update type-hints and callbacks to pass
    # EventStreamRpcMessageFlag instead of plain int.

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


class EventStreamRpcClientConnectionHandler(ABC):
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
            headers: Sequence[EventStreamHeader],
            payload: bytes,
            message_type: EventStreamRpcMessageType,
            flags: int,
            **kwargs) -> None:
        """Invoked when a message for the connection (stream-id 0) is received.

        Args:
            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from EventStreamRpcMessageFlag may be
                XORed together. Not all flags can be used with all message
                types, consult documentation.

            **kwargs: Forward compatibility kwargs.
        """

        pass


class EventStreamRpcClientConnection(NativeResource):
    """A client connection for the event-stream RPC protocol.

    Use :meth:`EventStreamRpcClientConnection.connect()` to establish a new
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
            handler: EventStreamRpcClientConnectionHandler,
            host_name: str,
            port: int,
            bootstrap: ClientBootstrap,
            socket_options: Optional[SocketOptions] = None,
            tls_connection_options: Optional[TlsConnectionOptions] = None) -> Future:
        """Asynchronously establish a new EventStreamRpcClientConnection.

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
            headers = [EventStreamHeader._from_binding_tuple(i) for i in headers]
            message_type = EventStreamRpcMessageType(message_type)
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
            headers = [EventStreamHeader._from_binding_tuple(i) for i in headers]
            message_type = EventStreamRpcMessageType(message_type)
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

    def close(self, reason=None):
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
            headers: Optional[Sequence[EventStreamHeader]] = [],
            payload: Optional[ByteString] = b'',
            message_type: EventStreamRpcMessageType,
            flags: int = EventStreamRpcMessageFlag.NONE,
            on_flush: Callable = None) -> Future:
        """Send a protocol message.

        Protocol messages use stream-id 0.

        Use the returned future, or the `on_flush` callback, to be informed
        when the message is successfully written to the wire, or fails to send.

        Keyword Args:
            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from EventStreamRpcMessageFlag may be
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
        headers = [i._as_binding_tuple() for i in headers]

        _awscrt.event_stream_rpc_client_connection_send_protocol_message(
            self._binding,
            headers,
            payload,
            message_type,
            flags,
            partial(self._on_flush, future, on_flush))
        return future

    def new_stream(self, handler: 'EventStreamRpcClientContinuationHandler') -> 'EventStreamClientContinuation':
        """
        Create a new stream.

        The stream will send no data until :meth:`EventStreamClientContinuation.activate()`
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
        return EventStreamRpcClientContinuation(binding, closed_future, self)


class EventStreamRpcClientContinuation(NativeResource):
    """
    A continuation of messages on a given stream-id.

    Create with :meth:`EventStreamRpcClientConnection.new_stream()`.

    The stream will send no data until :meth:`EventStreamClientContinuation.activate()`
    is called. Call activate() when you're ready for callbacks and events to fire.

    Attributes:
        connection (EventStreamRpcClientConnection): This stream's connection.

        closed_future (Future) : Future which completes with a result of None
            when the continuation has closed.
    """

    def __init__(self, binding, closed_future, connection):
        # Do not instantiate directly, use EventStreamRpcClientConnection.new_stream()
        super().__init__()
        self._binding = binding
        self.connection = connection  # type: EventStreamRpcClientConnection
        self.closed_future = closed_future  # type: Future

    def activate(
            self,
            *,
            operation: str,
            headers: Sequence[EventStreamHeader] = [],
            payload: ByteString = b'',
            message_type: EventStreamRpcMessageType,
            flags: int = EventStreamRpcMessageFlag.NONE,
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

            flags: Message flags. Values from EventStreamRpcMessageFlag may be
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
        headers = [i._as_binding_tuple() for i in headers]

        _awscrt.event_stream_rpc_client_continuation_activate(
            self._binding,
            operation,
            headers,
            payload,
            message_type,
            flags,
            partial(EventStreamRpcClientConnection._on_flush, flush_future, on_flush))

        return flush_future

    def send_message(
            self,
            *,
            headers: Sequence[EventStreamHeader] = [],
            payload: ByteString = b'',
            message_type: EventStreamRpcMessageType,
            flags: int = EventStreamRpcMessageFlag.NONE,
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

            flags: Message flags. Values from EventStreamRpcMessageFlag may be
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
        headers = [i._as_binding_tuple() for i in headers]

        _awscrt.event_stream_rpc_client_continuation_send_message(
            self._binding,
            headers,
            payload,
            message_type,
            flags,
            partial(EventStreamRpcClientConnection._on_flush, future, on_flush))
        return future

    def is_closed(self):
        return _awscrt.event_stream_rpc_client_continuation_is_closed(self._binding)


class EventStreamRpcClientContinuationHandler(ABC):
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
            headers: Sequence[EventStreamHeader],
            payload: bytes,
            message_type: EventStreamRpcMessageType,
            flags: int,
            **kwargs) -> None:
        """Invoked when a message is received on this continuation.

        Args:
            headers: Message headers.

            payload: Binary message payload.

            message_type: Message type.

            flags: Message flags. Values from EventStreamRpcMessageFlag may be
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
