"""
HTTP AsyncIO support

This module provides asyncio wrappers around the awscrt.http module.
All network operations in `awscrt.http_asyncio` are asynchronous and use Python's asyncio framework.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import asyncio
from concurrent.futures import Future
import awscrt.exceptions
from typing import List, Tuple, Optional, Union, Callable, Any
from awscrt.http import (
    HttpClientConnection, HttpRequest, HttpClientStream, HttpProxyOptions,
    Http2Setting, Http2ClientConnection, HttpConnectionBase, Http2ClientStream
)
from awscrt.io import (
    ClientBootstrap, SocketOptions, TlsConnectionOptions, InputStream
)
from collections import deque


class HttpClientConnectionAsync(HttpClientConnection):
    """
    An async HTTP client connection.

    Use `HttpClientConnectionAsync.new()` to establish a new connection.
    """
    __slots__ = ('_host_name', '_port')

    @classmethod
    async def new(cls,
                  host_name: str,
                  port: int,
                  bootstrap: Optional[ClientBootstrap] = None,
                  socket_options: Optional[SocketOptions] = None,
                  tls_connection_options: Optional[TlsConnectionOptions] = None,
                  proxy_options: Optional['HttpProxyOptions'] = None) -> "HttpClientConnectionAsync":
        """
        Asynchronously establish a new HttpClientConnectionAsync.

        Args:
            host_name (str): Connect to host.

            port (int): Connect to port.

            bootstrap (Optional [ClientBootstrap]): Client bootstrap to use when initiating socket connection.
                If None is provided, the default singleton is used.

            socket_options (Optional[SocketOptions]): Optional socket options.
                If None is provided, then default options are used.

            tls_connection_options (Optional[TlsConnectionOptions]): Optional TLS
                connection options. If None is provided, then the connection will
                be attempted over plain-text.

            proxy_options (Optional[HttpProxyOptions]): Optional proxy options.
                If None is provided then a proxy is not used.

        Returns:
            HttpClientConnectionAsync: A new HTTP client connection.
        """
        future = HttpClientConnection.new(
            host_name,
            port,
            bootstrap,
            socket_options,
            tls_connection_options,
            proxy_options)
        connection = await asyncio.wrap_future(future)
        return HttpClientConnectionAsync._from_connection(connection)

    @classmethod
    def _from_connection(cls, connection: HttpClientConnection) -> "HttpClientConnectionAsync":
        """Create an HttpClientConnectionAsync from an HttpClientConnection"""
        new_conn = cls.__new__(cls)
        # Copy the binding and properties from the original connection
        new_conn._binding = connection._binding
        new_conn._version = connection._version
        new_conn._host_name = connection._host_name
        new_conn._port = connection._port
        # Initialize the parent class without calling __init__
        HttpConnectionBase.__init__(new_conn)
        new_conn._shutdown_future = connection._shutdown_future
        return new_conn

    @property
    def host_name(self) -> str:
        """Remote hostname"""
        return self._host_name

    @property
    def port(self) -> int:
        """Remote port"""
        return self._port

    async def close(self) -> None:
        """Close the connection asynchronously.

        Shutdown is asynchronous. This call has no effect if the connection is already
        closing.

        Returns:
            None: When shutdown is complete.
        """
        close_future = super().close()
        await asyncio.wrap_future(close_future)

    def request(self,
                request: 'HttpRequest') -> 'HttpClientStreamAsync':
        """Create `HttpClientStreamAsync` to carry out the request/response exchange.

        Args:
            request (HttpRequest): Definition for outgoing request.

        Returns:
            HttpClientStreamAsync: Stream for the HTTP request/response exchange.
        """
        return HttpClientStreamAsync(self, request)


class Http2ClientConnectionAsync(HttpClientConnectionAsync):
    """
    An async HTTP/2 client connection.

    Use `Http2ClientConnectionAsync.new()` to establish a new connection.
    """

    @classmethod
    async def new(cls,
                  host_name: str,
                  port: int,
                  bootstrap: Optional[ClientBootstrap] = None,
                  socket_options: Optional[SocketOptions] = None,
                  tls_connection_options: Optional[TlsConnectionOptions] = None,
                  proxy_options: Optional['HttpProxyOptions'] = None,
                  initial_settings: Optional[List[Http2Setting]] = None,
                  on_remote_settings_changed: Optional[Callable[[List[Http2Setting]],
                                                                None]] = None) -> "Http2ClientConnectionAsync":
        """
        Asynchronously establish an HTTP/2 client connection.
        Notes: to set up the connection, the server must support HTTP/2 and TlsConnectionOptions

        This class extends HttpClientConnectionAsync with HTTP/2 specific functionality.

        HTTP/2 specific args:
            initial_settings (List[Http2Setting]): The initial settings to change for the connection.

            on_remote_settings_changed: Optional callback invoked once the remote peer changes its settings.
                And the settings are acknowledged by the local connection.
                The function should take the following arguments and return nothing:

                    *   `settings` (List[Http2Setting]): List of settings that were changed.
        """
        future = Http2ClientConnection.new(
            host_name,
            port,
            bootstrap,
            socket_options,
            tls_connection_options,
            proxy_options,
            initial_settings,
            on_remote_settings_changed)

        connection = await asyncio.wrap_future(future)
        return Http2ClientConnectionAsync._from_connection(connection)

    def request(self,
                request: 'HttpRequest',
                manual_write: bool = False) -> 'Http2ClientStreamAsync':
        """Create `Http2ClientStreamAsync` to carry out the request/response exchange.

        Args:
            request (HttpRequest): Definition for outgoing request.
            manual_write (bool): If True, enables manual data writing on the stream.

        Returns:
            Http2ClientStreamAsync: Stream for the HTTP/2 request/response exchange.
        """
        return Http2ClientStreamAsync(self, request, manual_write)


class HttpClientStreamAsync(HttpClientStream):
    """Async HTTP stream that sends a request and receives a response.

    Create an HttpClientStreamAsync with `HttpClientConnectionAsync.request()`.

    Attributes:
        connection (HttpClientConnectionAsync): This stream's connection.

        completion_future (asyncio.Future): Future that will contain
            the response status code (int) when the request/response exchange
            completes. If the exchange fails to complete, the Future will
            contain an exception indicating why it failed.
    """
    __slots__ = (
        '_response_status_future',
        '_response_headers_future',
        '_chunk_futures',
        '_received_chunks',
        '_completion_future',
        '_stream_completed')

    def __init__(self, connection: HttpClientConnectionAsync, request: HttpRequest) -> None:
        super()._init_common(connection, request)

    def _init_common(self, connection: HttpClientConnectionAsync,
                     request: HttpRequest,
                     http2_manual_write: bool = False) -> None:
        # Initialize the parent class
        super()._init_common(connection, request, http2_manual_write=http2_manual_write)

        # Set up async state tracking
        loop = asyncio.get_event_loop()
        self._chunk_futures = deque()
        self._received_chunks = deque()
        self._stream_completed = False

        # Create futures for async operations
        self._completion_future = loop.create_future()
        self._response_status_future = loop.create_future()
        self._response_headers_future = loop.create_future()

        # Activate the stream immediately
        self.activate()

    def _on_response(self, status_code: int, name_value_pairs: List[Tuple[str, str]]) -> None:
        self._response_status_future.set_result(status_code)
        self._response_headers_future.set_result(name_value_pairs)

    def _on_body(self, chunk: bytes) -> None:
        if self._chunk_futures:
            future = self._chunk_futures.popleft()
            future.set_result(chunk)
        else:
            self._received_chunks.append(chunk)

    def _on_complete(self, error_code: int) -> None:
        if error_code == 0:
            self._completion_future.set_result(self._response_status_future.result())
        else:
            self._completion_future.set_exception(awscrt.exceptions.from_code(error_code))

    async def next(self) -> bytes:
        """Get the next chunk from the response body.

        Returns:
            bytes: The next chunk of data from the response body.
                Returns empty bytes when the stream is completed and no more chunks are left.
        """
        if self._received_chunks:
            return self._received_chunks.popleft()
        elif self._completion_future.done():
            return b""
        else:
            future = Future[bytes]()
            self._chunk_futures.append(future)
            return await asyncio.wrap_future(future)

    async def wait_for_completion(self) -> int:
        """Wait asynchronously for the stream to complete.

        Returns:
            int: The response status code.
        """
        return await self._completion_future

    async def response_status_code(self) -> int:
        """Get the response status code asynchronously.

        Returns:
            int: The response status code.
        """
        return await self._response_status_future

    async def response_headers(self) -> List[Tuple[str, str]]:
        """Get the response headers asynchronously.

        Returns:
            List[Tuple[str, str]]: The response headers as a list of (name, value) tuples.
        """
        return await self._response_headers_future


class Http2ClientStreamAsync(HttpClientStreamAsync, Http2ClientStream):
    """HTTP/2 stream that sends a request and receives a response.

    Create an Http2ClientStreamAsync with `Http2ClientConnectionAsync.request()`.
    """

    def __init__(self, connection: HttpClientConnectionAsync, request: HttpRequest, manual_write: bool) -> None:
        super()._init_common(connection, request, http2_manual_write=manual_write)

    async def write_data_async(self,
                               data_stream: Union[InputStream, Any],
                               end_stream: bool = False) -> None:
        """Write data to the stream asynchronously.

        Args:
            data_stream (Union[InputStream, Any]): Data to write.
            end_stream (bool): Whether this is the last data to write.

        Returns:
            None: When the write completes.
        """
        future = self.write_data(data_stream, end_stream)
        await asyncio.wrap_future(future)
