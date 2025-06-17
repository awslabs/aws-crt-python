"""
HTTP AsyncIO support

This module provides asyncio wrappers around the awscrt.http module.
All network operations in `awscrt.http_asyncio` are asynchronous and use Python's asyncio framework.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import asyncio
import io
import _awscrt
from concurrent.futures import Future
import awscrt.exceptions
from typing import List, Tuple, Optional, Union, Callable, Any, AsyncIterator
from awscrt.http import (
    HttpClientConnectionBase, HttpRequest, HttClientStreamBase, HttpProxyOptions,
    Http2Setting, HttpVersion
)
from awscrt.io import (
    ClientBootstrap, SocketOptions, TlsConnectionOptions, InputStream
)
from collections import deque


class HttpClientConnectionAsync(HttpClientConnectionBase):
    """
    An async HTTP client connection.

    Use `HttpClientConnectionAsync.new()` to establish a new connection.
    """

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
        future = cls._generic_new(
            host_name,
            port,
            bootstrap,
            socket_options,
            tls_connection_options,
            proxy_options,
            asyncio_connection=True)
        return await asyncio.wrap_future(future)

    async def close(self) -> None:
        """Close the connection asynchronously.

        Shutdown is asynchronous. This call has no effect if the connection is already
        closing.

        Returns:
            None: When shutdown is complete.
        """
        _awscrt.http_connection_close(self._binding)
        await asyncio.wrap_future(self.shutdown_future)

    def request(self,
                request: 'HttpRequest',
                loop: Optional[asyncio.AbstractEventLoop] = None) -> 'HttpClientStreamAsync':
        """Create `HttpClientStreamAsync` to carry out the request/response exchange.

        Args:
            request (HttpRequest): Definition for outgoing request.
            loop (Optional[asyncio.AbstractEventLoop]): Event loop to use for async operations.
                If None, the current event loop is used.

        Returns:
            HttpClientStreamAsync: Stream for the HTTP request/response exchange.
        """
        return HttpClientStreamAsync(self, request, loop)


class Http2ClientConnectionAsync(HttpClientConnectionBase):
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
        future = cls._generic_new(
            host_name,
            port,
            bootstrap,
            socket_options,
            tls_connection_options,
            proxy_options,
            HttpVersion.Http2,
            initial_settings,
            on_remote_settings_changed,
            asyncio_connection=True)
        return await asyncio.wrap_future(future)

    async def close(self) -> None:
        """Close the connection asynchronously.

        Shutdown is asynchronous. This call has no effect if the connection is already
        closing.

        Returns:
            None: When shutdown is complete.
        """
        _awscrt.http_connection_close(self._binding)
        await asyncio.wrap_future(self.shutdown_future)

    def request(self,
                request: 'HttpRequest',
                manual_write: bool = False,
                loop: Optional[asyncio.AbstractEventLoop] = None) -> 'Http2ClientStreamAsync':
        """Create `Http2ClientStreamAsync` to carry out the request/response exchange.

        Args:
            request (HttpRequest): Definition for outgoing request.
            manual_write (bool): If True, enables manual data writing on the stream.
            loop (Optional[asyncio.AbstractEventLoop]): Event loop to use for async operations.
                If None, the current event loop is used.

        Returns:
            Http2ClientStreamAsync: Stream for the HTTP/2 request/response exchange.
        """
        return Http2ClientStreamAsync(self, request, manual_write, loop)


class HttpClientStreamAsyncBase(HttClientStreamBase):
    __slots__ = (
        '_response_status_future',
        '_response_headers_future',
        '_chunk_futures',
        '_received_chunks',
        '_completion_future',
        '_stream_completed',
        '_status_code',
        '_loop')

    def _init_common(self, connection: HttpClientConnectionAsync,
                     request: HttpRequest,
                     http2_manual_write: bool = False,
                     loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        # Initialize the parent class
        super()._init_common(connection, request, http2_manual_write=http2_manual_write)

        # Attach the event loop for async operations
        if loop is None:
            # Use the current event loop if none is provided
            loop = asyncio.get_event_loop()
        elif not isinstance(loop, asyncio.AbstractEventLoop):
            raise TypeError("loop must be an instance of asyncio.AbstractEventLoop")
        self._loop = loop

        # deque is thread-safe for appending and popping, so that we don't need
        # locks to handle the callbacks from the C thread
        self._chunk_futures = deque()
        self._received_chunks = deque()
        self._stream_completed = False

        # Create futures for async operations
        self._completion_future = self._loop.create_future()
        self._response_status_future = self._loop.create_future()
        self._response_headers_future = self._loop.create_future()
        self._status_code = None

        # Activate the stream immediately
        _awscrt.http_client_stream_activate(self)

    def _on_response(self, status_code: int, name_value_pairs: List[Tuple[str, str]]) -> None:
        self._status_code = status_code
        # invoked from the C thread, so we need to schedule the result setting on the event loop
        self._loop.call_soon_threadsafe(self._set_response, status_code, name_value_pairs)

    def _set_response(self, status_code: int, name_value_pairs: List[Tuple[str, str]]) -> None:
        """Set the response status and headers in the futures."""
        self._response_status_future.set_result(status_code)
        self._response_headers_future.set_result(name_value_pairs)

    def _on_body(self, chunk: bytes) -> None:
        self._loop.call_soon_threadsafe(self._set_body_chunk, chunk)

    def _set_body_chunk(self, chunk: bytes) -> None:
        """Process body chunk on the correct event loop thread."""
        if self._chunk_futures:
            future = self._chunk_futures.popleft()
            future.set_result(chunk)
        else:
            self._received_chunks.append(chunk)

    def _on_complete(self, error_code: int) -> None:
        # invoked from the C thread, so we need to schedule the result setting on the event loop
        self._loop.call_soon_threadsafe(self._set_completion, error_code)

    def _set_completion(self, error_code: int) -> None:
        """Set the completion status of the stream."""
        if error_code == 0:
            self._completion_future.set_result(self._status_code)
        else:
            self._completion_future.set_exception(awscrt.exceptions.from_code(error_code))

        if self._chunk_futures:
            # the stream is completed, so we need to set the futures
            future = self._chunk_futures.popleft()
            future.set_result("")

    async def get_response_status_code(self) -> int:
        """Get the response status code asynchronously.

        Returns:
            int: The response status code.
        """
        return await self._response_status_future

    async def get_response_headers(self) -> List[Tuple[str, str]]:
        """Get the response headers asynchronously.

        Returns:
            List[Tuple[str, str]]: The response headers as a list of (name, value) tuples.
        """
        return await self._response_headers_future

    async def get_next_response_chunk(self) -> bytes:
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
            future = Future()
            self._chunk_futures.append(future)
            return await asyncio.wrap_future(future, loop=self._loop)

    async def wait_for_completion(self) -> int:
        """Wait asynchronously for the stream to complete.

        Returns:
            int: The response status code.
        """
        return await self._completion_future


class HttpClientStreamAsync(HttpClientStreamAsyncBase):
    """Async HTTP stream that sends a request and receives a response.

    Create an HttpClientStreamAsync with `HttpClientConnectionAsync.request()`.

    Attributes:
        connection (HttpClientConnectionAsync): This stream's connection.

        completion_future (asyncio.Future): Future that will contain
            the response status code (int) when the request/response exchange
            completes. If the exchange fails to complete, the Future will
            contain an exception indicating why it failed.

    Notes:
        All async method on a stream (await stream.next(), etc.) must be performed in the
        thread that owns the event loop used to create the stream
    """

    def __init__(self, connection: HttpClientConnectionAsync, request: HttpRequest,
                 loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Initialize an HTTP client stream.

        Args:
            connection (HttpClientConnectionAsync): The connection to send the request on.
            request (HttpRequest): The HTTP request to send.
            loop (Optional[asyncio.AbstractEventLoop]): Event loop to use for async operations.
                If None, the current event loop is used.
        """
        super()._init_common(connection, request, loop=loop)


class Http2ClientStreamAsync(HttpClientStreamAsyncBase):
    """HTTP/2 stream that sends a request and receives a response.

    Create an Http2ClientStreamAsync with `Http2ClientConnectionAsync.request()`.
    """

    def __init__(self, connection: HttpClientConnectionAsync, request: HttpRequest, manual_write: bool,
                 loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        super()._init_common(connection, request, http2_manual_write=manual_write, loop=loop)

    async def write_data(self,
                         data_stream: Union[InputStream, Any],
                         end_stream: bool = False) -> None:
        """Write data to the stream asynchronously.

        Args:
            data_stream (AsyncIterator[bytes]): Async iterator that yields bytes to write.
                Can be None to write an empty body, which is useful to finalize a request
                with end_stream=True.
            end_stream (bool): Whether this is the last data to write.

        Returns:
            None: When the write completes.
        """
        future: Future = Future()
        body_stream: InputStream = InputStream.wrap(data_stream, allow_none=True)

        def on_write_complete(error_code: int) -> None:
            if future.cancelled():
                # the future was cancelled, so we don't need to set the result or exception
                return
            if error_code:
                future.set_exception(awscrt.exceptions.from_code(error_code))
            else:
                future.set_result(None)

        _awscrt.http2_client_stream_write_data(self, body_stream, end_stream, on_write_complete)
        await asyncio.wrap_future(future)
