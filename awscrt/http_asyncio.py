"""
HTTP AsyncIO support

This module provides asyncio wrappers around the awscrt.http module.
All network operations in `awscrt.http_asyncio` are asynchronous and use Python's asyncio framework.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
import asyncio
from concurrent.futures import Future
from awscrt import NativeResource
import awscrt.exceptions
from typing import List, Tuple, Dict, Optional, Union, Iterator, Callable, Any
from awscrt.http import (
    HttpVersion, HttpClientConnection, HttpRequest, HttpClientStream, HttpProxyOptions,
    Http2Setting, Http2ClientConnection, HttpConnectionBase, HttpHeaders, Http2ClientStream
)
from awscrt.io import (
    ClientBootstrap, SocketOptions, TlsConnectionOptions, InputStream
)
from collections import deque


def _future_to_async(future: Future) -> asyncio.Future:
    """Convert a concurrent.futures.Future to asyncio.Future"""
    loop = asyncio.get_event_loop()
    async_future = loop.create_future()

    def _on_done(fut):
        try:
            result = fut.result()
            loop.call_soon_threadsafe(async_future.set_result, result)
        except Exception as e:
            loop.call_soon_threadsafe(async_future.set_exception, e)

    future.add_done_callback(_on_done)
    return async_future


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
    def _from_connection(cls, connection):
        """Create an HttpClientConnectionAsync from an HttpClientConnection"""
        new_conn = cls.__new__(cls)
        # Copy the binding and properties from the original connection
        new_conn._binding = connection._binding
        new_conn._shutdown_future = connection._shutdown_future
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
                request: 'HttpRequest',
                on_response: Optional[Callable[...,
                                               None]] = None,
                on_body: Optional[Callable[...,
                                           None]] = None) -> 'Http2ClientStreamAsync':
        """Create `HttpClientStreamAsync` to carry out the request/response exchange.

        NOTE: The HTTP stream sends no data until `HttpClientStreamAsync.activate()`
        is called. Call activate() when you're ready for callbacks and events to fire.

        Args:
            request (HttpRequest): Definition for outgoing request.

            on_response: Optional callback invoked once main response headers are received.
                The function should take the following arguments and return nothing:

                    *   `http_stream` (`HttpClientStreamAsync`): HTTP stream carrying
                        out this request/response exchange.

                    *   `status_code` (int): Response status code.

                    *   `headers` (List[Tuple[str, str]]): Response headers as a
                        list of (name,value) pairs.

                    *   `**kwargs` (dict): Forward compatibility kwargs.

                An exception raise by this function will cause the HTTP stream to end in error.
                This callback is always invoked on the connection's event-loop thread.

            on_body: Optional callback invoked 0+ times as response body data is received.
                The function should take the following arguments and return nothing:

                    *   `http_stream` (`HttpClientStreamAsync`): HTTP stream carrying
                        out this request/response exchange.

                    *   `chunk` (buffer): Response body data (not necessarily
                        a whole "chunk" of chunked encoding).

                    *   `**kwargs` (dict): Forward-compatibility kwargs.

                An exception raise by this function will cause the HTTP stream to end in error.
                This callback is always invoked on the connection's event-loop thread.

        Returns:
            If use_response_wrapper is False:
                HttpClientStreamAsync: Stream for the HTTP request/response exchange.
            If use_response_wrapper is True:
                Tuple[HttpClientStreamAsync, HttpResponseAsync]: A tuple containing the stream
                and a response wrapper that provides async methods to access the response.
        """
        stream = HttpClientStream(self, request, on_response, on_body)
        async_stream = HttpClientStreamAsync._from_stream(stream)

        return async_stream


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
                on_response: Optional[Callable[...,
                                               None]] = None,
                on_body: Optional[Callable[...,
                                           None]] = None,
                manual_write: bool = False) -> 'Http2ClientStreamAsync':
        """Create `Http2ClientStreamAsync` to carry out the request/response exchange.

        Args:
            request (HttpRequest): Definition for outgoing request.
            on_response: Optional callback invoked once main response headers are received.
            on_body: Optional callback invoked 0+ times as response body data is received.
            manual_write (bool): If True, enables manual data writing on the stream.

        Returns:
            Http2ClientStreamAsync: Stream for the HTTP/2 request/response exchange.
        """
        print("######################### async request called #########################")
        stream = Http2ClientStream(self, request, on_response, on_body, manual_write)
        async_stream = Http2ClientStreamAsync._from_stream(stream)

        return async_stream


class HttpClientStreamAsync(HttpClientStream):
    """Async HTTP stream that sends a request and receives a response.

    Create an HttpClientStreamAsync with `HttpClientConnectionAsync.request()`.

    NOTE: The HTTP stream sends no data until `HttpClientStreamAsync.activate()`
    is called. Call activate() when you're ready for callbacks and events to fire.

    Attributes:
        connection (HttpClientConnectionAsync): This stream's connection.

        completion_future (asyncio.Future): Future that will contain
            the response status code (int) when the request/response exchange
            completes. If the exchange fails to complete, the Future will
            contain an exception indicating why it failed.
    """
    __slots__ = (
        '_response_status_code',
        '_on_response_cb',
        '_on_body_cb',
        '_request',
        '_version',
        '_original_stream',
        '_completion_future',
        '_chunk_queue',
        '_stream_completed',
        '_original_on_body_cb')

    @classmethod
    def _from_stream(cls, stream: HttpClientStream) -> 'HttpClientStreamAsync':
        """Create an HttpClientStreamAsync from an HttpClientStream"""
        new_stream = cls.__new__(cls)
        # Keep a reference to the original stream to prevent garbage collection
        new_stream._original_stream = stream
        # Copy the binding and properties from the original stream
        new_stream._binding = stream._binding
        new_stream._connection = stream._connection

        # Initialize chunk queue and stream completion flag
        new_stream._chunk_futures = deque()
        new_stream._stream_completed = False
        new_stream._received_chunks = deque()

        # Capture the current event loop to use in callbacks
        loop = asyncio.get_event_loop()
        new_stream._completion_future = loop.create_future()

        # Add a callback to bridge the original future to the asyncio future
        def _on_done(fut):
            try:
                result = fut.result()
                loop.call_soon_threadsafe(new_stream._completion_future.set_result, result)
                # Mark the stream as completed when the completion_future resolves
                loop.call_soon_threadsafe(lambda: setattr(new_stream, '_stream_completed', True))
            except Exception as e:
                loop.call_soon_threadsafe(new_stream._completion_future.set_exception, e)
                # Mark the stream as completed on error as well
                loop.call_soon_threadsafe(lambda: setattr(new_stream, '_stream_completed', True))

        stream._completion_future.add_done_callback(_on_done)

        # Create a new on_body_cb that puts chunks in the queue
        def wrapped_on_body_cb(http_stream, chunk, **kwargs):
            # print("################# chunk is", chunk)
            if new_stream._chunk_futures:
                # print("################# chunk in future is", chunk)
                future = new_stream._chunk_futures.popleft()
                future.set_result(chunk)
            else:
                # print("################# chunk in recoved is", chunk)
                new_stream._received_chunks.append(chunk)

        # Replace the on_body_cb with our wrapper
        stream._on_body_cb = wrapped_on_body_cb
        new_stream._on_body_cb = wrapped_on_body_cb

        new_stream._response_status_code = stream._response_status_code
        new_stream._on_response_cb = stream._on_response_cb
        new_stream._request = stream._request
        new_stream._version = stream._version

        return new_stream

    def activate(self) -> None:
        print("######################### async activate called #########################")
        """Begin sending the request.

        The HTTP stream does nothing until this is called. Call activate() when you
        are ready for its callbacks and events to fire.
        """
        # Use the original stream's binding
        self._original_stream.activate()

    async def next(self) -> bytes:
        # print("######################### async next called #########################")
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


class Http2ClientStreamAsync(HttpClientStreamAsync):
    """HTTP/2 stream that sends a request and receives a response.

    Create an Http2ClientStreamAsync with `Http2ClientConnectionAsync.request()`.
    """

    async def write_data(self,
                         data_stream: Union[InputStream, Any],
                         end_stream: bool = False) -> None:
        """Write data to the stream asynchronously.

        Args:
            data_stream (Union[InputStream, Any]): Data to write.
            end_stream (bool): Whether this is the last data to write.

        Returns:
            None: When the write completes.
        """
        # print("######################### async write_data called #########################")
        future = self._original_stream.write_data(data_stream, end_stream)
        await asyncio.wrap_future(future)
