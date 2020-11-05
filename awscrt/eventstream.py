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
from concurrent.futures import Future
from functools import partial
from typing import Optional
import weakref


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
        self.connection = None

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
    def on_protocol_message(self, **kwargs) -> None:
        # TODO define signature
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
    def _on_protocol_message(bound_weak_header, headers, payload, message_type, flags):
        handler = bound_weak_handler()
        if handler:
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
