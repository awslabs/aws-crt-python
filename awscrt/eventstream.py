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
from collections.abc import ByteString
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
    class:`EventStreamHeaderType` enumerates the supported value types.
    """

    def __init__(self, name: str, value: Any, header_type: EventStreamHeaderType):
        # do not call directly, use EventStreamHeader.from_xyz() methods.
        self._name = name
        self._value = value
        self._type = header_type

    @classmethod
    def from_bool(cls, name: str, value: bool) -> 'EventStreamHeader':
        if value:
            return cls(name, True, EventStreamHeaderType.BOOL_TRUE)
        else:
            return cls(name, False, EventStreamHeaderType.BOOL_FALSE)

    @classmethod
    def from_byte(cls, name: str, value: int) -> 'EventStreamHeader':
        value = int(value)
        if value < _BYTE_MIN or value > _BYTE_MAX:
            raise ValueError("Value {} cannot fit in signed 8-bit byte".format(value))
        return cls(name, value, EventStreamHeaderType.BYTE)

    @classmethod
    def from_int16(cls, name: str, value: int) -> 'EventStreamHeader':
        value = int(value)
        if value < _INT16_MIN or value > _INT16_MAX:
            raise ValueError("Value {} cannot fit in signed 16-bit int".format(value))
        return cls(name, value, EventStreamHeaderType.INT16)

    @classmethod
    def from_int32(cls, name: str, value: int) -> 'EventStreamHeader':
        value = int(value)
        if value < _INT32_MIN or value > _INT32_MAX:
            raise ValueError("Value {} cannot fit in signed 32-bit int".format(value))
        return cls(name, value, EventStreamHeaderType.INT32)

    @classmethod
    def from_int64(cls, name: str, value: int) -> 'EventStreamHeader':
        value = int(value)
        if value < _INT64_MIN or value > _INT64_MAX:
            raise ValueError("Value {} cannot fit in signed 64-bit int".format(value))
        return cls(name, value, EventStreamHeaderType.INT64)

    @classmethod
    def from_byte_buf(cls, name: str, value: ByteString) -> 'EventStreamHeader':
        return cls(name, value, EventStreamHeaderType.BYTE_BUF)

    @classmethod
    def from_string(cls, name: str, value: str) -> 'EventStreamHeader':
        value = str(value)
        return cls(name, value, EventStreamHeaderType.STRING)

    @classmethod
    def from_timestamp(cls, name: str, value: int) -> 'EventStreamHeader':
        value = int(value)
        if value < _INT64_MIN or value > _INT64_MAX:
            raise ValueError("Value {} exceeds timestamp limits".format(value))
        return cls(name, value, EventStreamHeaderType.TIMESTAMP)

    @classmethod
    def from_uuid(cls, name: str, value: UUID) -> 'EventStreamHeader':
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
        return self._name

    @property
    def type(self) -> EventStreamHeaderType:
        return self._type

    @property
    def value(self) -> Any:
        return self._value

    def _value_as(self, header_type: EventStreamHeaderType) -> Any:
        if self._type != header_type:
            raise TypeError("Header type is {}, not {}".format(self._type, header_type))
        return self._value

    def value_as_bool(self) -> bool:
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
        return self._value_as(EventStreamHeaderType.BYTE)

    def value_as_int16(self) -> int:
        return self._value_as(EventStreamHeaderType.INT16)

    def value_as_int32(self) -> int:
        return self._value_as(EventStreamHeaderType.INT32)

    def value_as_int64(self) -> int:
        return self._value_as(EventStreamHeaderType.INT64)

    def value_as_byte_buf(self) -> ByteString:
        return self._value_as(EventStreamHeaderType.BYTE_BUF)

    def value_as_string(self) -> str:
        return self._value_as(EventStreamHeaderType.STRING)

    def value_as_timestamp(self) -> int:
        return self._value_as(EventStreamHeaderType.TIMESTAMP)

    def value_as_uuid(self) -> UUID:
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

    Different message types expect specific headers and flags, consult documentation."""
    # TODO: flesh out these docs

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
    """Connect acknowledgement"""

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
    Not all flags can be used with all messages types, consult documentation.
    """
    # TODO: flesh out these docs

    # TODO: when python 3.5 is dropped this class should inherit from IntFlag.
    # When doing this, be sure to update type-hints and callbacks to pass
    # EventStreamRpcMessageFlag instead of plain int.

    NONE = 0
    """No flags"""

    CONNECTION_ACCEPTED = 0x1
    """Connection accepted

    If this flag is absent from a CONNECT_ACK, the connection has been rejected."""

    TERMINATE_STREAM = 0x2
    """Terminate stream"""

    def __format__(self, format_spec):
        # override so formatted string doesn't simply look like an int
        return str(self)


class EventStreamRpcClientConnectionHandler(ABC):
    """Base class for handling connection events.

    Inherit from this class and override functions to handle connection events.
    All events for this connection will be invoked on the same thread,
    and `on_connection_setup()` will always be the first event invoked.
    The `connection` property will be set before any events are invoked.
    If the connect attempt is unsuccessful, no events will be invoked.

    Note that the `on_connection_shutdown()` event will not be invoked
    if the handler is garbage-collected before the connection's internal
    resources finish shutting down.

    Attributes:
        connection (Optional[EventStreamRpcClientConnection]): Initially None.
            Will be set to the actual connection before any events are invoked.
    """

    def __init__(self):
        self.connection = None  # type: Optional[EventStreamRpcClientConnection]

    @abstractmethod
    def on_connection_setup(self, **kwargs) -> None:
        """Invoked when connection has been successfully established.

        This will always be the first callback invoked on the handler.
        """
        pass

    @abstractmethod
    def on_connection_shutdown(self, reason: Optional[Exception], **kwargs) -> None:
        """Invoked when the connection finishes shutting down.

        Note that this event will not be invoked if the handler is
        garbage-collected before the shutdown process completes"""
        pass

    @abstractmethod
    def on_protocol_message(
            self,
            headers: Sequence[EventStreamHeader],
            payload: bytes,
            message_type: EventStreamRpcMessageType,
            flags: int,
            **kwargs) -> None:
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
        self.host_name = host_name
        self.port = port
        self.shutdown_future = Future()

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
            TODO (int): fill this out
        Returns:
            concurrent.futures.Future: A Future which completes when the connection succeeds or fails.
            If successful, the Future will contain None.
            Otherwise it will contain an exception.
            If the connection is successful, it is accessible via `handler.connection`.
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

        connection._binding = _awscrt.event_stream_rpc_client_connection_connect(
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
    def _on_connection_setup(bound_future, bound_handler, bound_connection, error_code):
        try:
            if error_code:
                e = awscrt.exceptions.from_code(error_code)
                bound_future.set_exception(e)
            else:
                bound_handler.connection = bound_connection
                bound_handler.on_connection_setup()
                bound_future.set_result(None)
        except Exception as e:
            # user callback had unhandled exception, set future as failed
            bound_future.set_exception(e)
            raise

    @staticmethod
    def _on_connection_shutdown(bound_future, bound_weak_handler, error_code):
        reason = awscrt.exceptions.from_code(error_code) if error_code else None
        try:
            handler = bound_weak_handler()
            if handler:
                handler.on_connection_shutdown(reason=reason)
        finally:
            # user callback had unhandled exception, use finally to ensure future gets set
            if reason:
                bound_future.set_exception(reason)
            else:
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
            headers: Optional[Sequence[EventStreamHeader]] = [],
            payload: Optional[ByteString] = b'',
            message_type: EventStreamRpcMessageType,
            flags: int = EventStreamRpcMessageFlag.NONE) -> Future:
        """Send a protocol message.

        Protocol messages use stream 0.

        Keyword Args:
            headers: Message headers.
            payload: Binary message payload.
            message_type: Message type.
            flags: Message flags. Values from EventStreamRpcMessageFlag may be
                XORed together. Not all flags can be used with all messages
                types, consult documentation.
        Returns:
            A future which completes with a result of None if the the message
            successfully written to the wire. This is still no guarantee
            that the peer received or processed the message.
            The future will complete with an exception if the connection
            is closed before the message can be sent.

        """

        future = Future()

        def _on_flush(error_code):
            if error_code:
                e = awscrt.exceptions.from_code(error_code)
                future.set_exception(e)
            else:
                future.set_result(None)

        # native code deals with simplified types
        headers = [i._as_binding_tuple() for i in headers]

        _awscrt.event_stream_rpc_client_connection_send_protocol_message(
            self._binding, headers, payload, message_type, flags, _on_flush)
        return future
