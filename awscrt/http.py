"""
HTTP

All network operations in `awscrt.http` are asynchronous.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from concurrent.futures import Future
from awscrt import NativeResource
import awscrt.exceptions
from awscrt.io import ClientBootstrap, InputStream, TlsConnectionOptions, SocketOptions
from enum import IntEnum
from typing import List, Tuple, Dict, Optional, Union, Iterator, Callable, Any


class HttpVersion(IntEnum):
    """HTTP protocol version enumeration"""
    Unknown = 0  #: Unknown
    Http1_0 = 1  #: HTTP/1.0
    Http1_1 = 2  #: HTTP/1.1
    Http2 = 3  #: HTTP/2


class Http2SettingID(IntEnum):
    """HTTP/2 Predefined settings(RFC-9113 6.5.2)."""
    HEADER_TABLE_SIZE = 1
    ENABLE_PUSH = 2
    MAX_CONCURRENT_STREAMS = 3
    INITIAL_WINDOW_SIZE = 4
    MAX_FRAME_SIZE = 5
    MAX_HEADER_LIST_SIZE = 6


class Http2Setting:
    """HTTP/2 Setting.
    Settings are very complicated in HTTP/2.
    Each end has its own settings, and the local settings cannot be applied
    until the remote end acknowledges it.
    Each end can change its settings at any time, while the order of the settings
    changed may also result in different behavior.

    Each setting has its boundary and initial values defined in RFC-9113 6.5.2:
    Initial values are listed below, while the range can be found in VALID_RANGES:
    HEADER_TABLE_SIZE: 4096
    ENABLE_PUSH: 1
    MAX_CONCURRENT_STREAMS: 2^32-1
    INITIAL_WINDOW_SIZE: 2^16-1
    MAX_FRAME_SIZE: 2^14
    MAX_HEADER_LIST_SIZE: 2^32-1

    Args:
        id (Http2SettingID): Setting ID.
        value (int): Setting value.
    """
    VALID_RANGES: Dict[Http2SettingID, Tuple[int, int]] = {
        Http2SettingID.HEADER_TABLE_SIZE: (0, 2**32 - 1),
        Http2SettingID.ENABLE_PUSH: (0, 1),
        Http2SettingID.MAX_CONCURRENT_STREAMS: (0, 2**32 - 1),
        Http2SettingID.INITIAL_WINDOW_SIZE: (0, 2**31 - 1),
        Http2SettingID.MAX_FRAME_SIZE: (2**14, 2**24 - 1),
        Http2SettingID.MAX_HEADER_LIST_SIZE: (0, 2**32 - 1),
    }

    def __init__(self, id: Http2SettingID, value: int) -> None:
        assert isinstance(id, Http2SettingID)
        assert isinstance(value, int)
        self.id = id

        # Verify value is within allowed range for the given setting
        self._validate_setting_value(id, value)
        self.value = value

    def _validate_setting_value(self, id: Http2SettingID, value: int) -> None:
        """Validate that setting value is within its allowed range according to RFC-9113 6.5.2."""
        min_value, max_value = self.VALID_RANGES[id]
        if not min_value <= value <= max_value:
            setting_name = id.name
            raise ValueError(f"{setting_name} must be between {min_value} and {max_value}, got {value}")

    def __str__(self) -> str:
        return self.__class__.__name__ + f"({self.id.name}={self.value})"


class HttpConnectionBase(NativeResource):
    """Base for HTTP connection classes."""

    __slots__ = ('_shutdown_future', '_version')

    def __init__(self) -> None:
        super().__init__()
        self._shutdown_future = Future()

    @property
    def shutdown_future(self) -> "concurrent.futures.Future":
        """
        concurrent.futures.Future: Completes when this connection has finished shutting down.
        Future will contain a result of None, or an exception indicating why shutdown occurred.
        Note that the connection may have been garbage-collected before this future completes.
        """
        return self._shutdown_future

    @property
    def version(self) -> HttpVersion:
        """HttpVersion: Protocol used by this connection"""
        return self._version

    def is_open(self) -> bool:
        """
        Returns:
            bool: True if this connection is open and usable, False otherwise.
            Check :attr:`shutdown_future` to know when the connection is completely
            finished shutting down.
        """
        return _awscrt.http_connection_is_open(self._binding)


class HttpClientConnectionBase(HttpConnectionBase):
    __slots__ = ('_host_name', '_port')

    @staticmethod
    def _generic_new(
            host_name: str,
            port: int,
            bootstrap: Optional[ClientBootstrap] = None,
            socket_options: Optional[SocketOptions] = None,
            tls_connection_options: Optional[TlsConnectionOptions] = None,
            proxy_options: Optional['HttpProxyOptions'] = None,
            expected_version: Optional[HttpVersion] = None,
            initial_settings: Optional[List[Http2Setting]] = None,
            on_remote_settings_changed: Optional[Callable[[List[Http2Setting]], None]] = None,
            asyncio_connection=False,
            manual_window_management: bool = False,
            initial_window_size: Optional[int] = None,
            read_buffer_capacity: Optional[int] = None,
            conn_manual_window_management: bool = False,
            conn_window_size_threshold: Optional[int] = None,
            stream_window_size_threshold: Optional[int] = None) -> "concurrent.futures.Future":
        """
        Initialize the generic part of the HttpClientConnection class.
        """
        assert isinstance(bootstrap, ClientBootstrap) or bootstrap is None
        assert isinstance(host_name, str)
        assert isinstance(port, int)
        assert isinstance(tls_connection_options, TlsConnectionOptions) or tls_connection_options is None
        assert isinstance(socket_options, SocketOptions) or socket_options is None
        assert isinstance(proxy_options, HttpProxyOptions) or proxy_options is None

        future = Future()

        try:
            if not socket_options:
                socket_options = SocketOptions()

            if not bootstrap:
                bootstrap = ClientBootstrap.get_or_create_static_default()

            connection_core = _HttpClientConnectionCore(
                host_name,
                port,
                bootstrap=bootstrap,
                tls_connection_options=tls_connection_options,
                connect_future=future,
                expected_version=expected_version,
                on_remote_settings_changed=on_remote_settings_changed,
                asyncio_connection=asyncio_connection)

            _awscrt.http_client_connection_new(
                bootstrap,
                host_name,
                port,
                socket_options,
                tls_connection_options,
                proxy_options,
                initial_settings,
                on_remote_settings_changed,
                connection_core,
                manual_window_management,
                initial_window_size,
                read_buffer_capacity,
                conn_manual_window_management,
                conn_window_size_threshold,
                stream_window_size_threshold)

        except Exception as e:
            future.set_exception(e)

        return future

    @property
    def host_name(self) -> str:
        """Remote hostname"""
        return self._host_name

    @property
    def port(self) -> int:
        """Remote port"""
        return self._port


class HttpClientConnection(HttpClientConnectionBase):
    """
    An HTTP client connection.

    Use :meth:`HttpClientConnection.new()` to establish a new connection.
    """
    __slots__ = ('_host_name', '_port')

    @classmethod
    def new(cls,
            host_name: str,
            port: int,
            bootstrap: Optional[ClientBootstrap] = None,
            socket_options: Optional[SocketOptions] = None,
            tls_connection_options: Optional[TlsConnectionOptions] = None,
            proxy_options: Optional['HttpProxyOptions'] = None,
            manual_window_management: bool = False,
            initial_window_size: Optional[int] = None,
            read_buffer_capacity: Optional[int] = None) -> "concurrent.futures.Future":
        """
        Asynchronously establish a new HttpClientConnection.

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

            manual_window_management (bool): Set to True to manually manage the flow-control window
                of each stream. If False, the connection maintains flow-control windows such that
                no back-pressure is applied and data arrives as fast as possible. If True, the
                flow-control window of each stream shrinks as body data is received (headers,
                padding, and other metadata do not affect the window). `initial_window_size`
                determines the starting size of each stream's window. When a stream's window
                reaches 0, no further data is received until `update_window()` is called.
                Default is False.

            initial_window_size (Optional[int]): The starting size of each stream's flow-control
                window. Required if `manual_window_management` is True, ignored otherwise.
                Must be <= 2^31-1 or connection fails. If set to 0 with `manual_window_management`
                True, streams start with zero window.
                Required if manual_window_management is True, ignored otherwise.

            read_buffer_capacity (Optional[int]): Capacity in bytes of the HTTP/1.1 connection's
                read buffer. The buffer grows when the flow-control window of the incoming stream
                reaches zero. Ignored if `manual_window_management` is False. A capacity that is
                too small may hinder throughput. A capacity that is too large may waste memory
                without improving throughput. If None or zero, a default value is used.

        Returns:
            concurrent.futures.Future: A Future which completes when connection succeeds or fails.
            If successful, the Future will contain a new :class:`HttpClientConnection`.
            Otherwise, it will contain an exception.
        """
        return cls._generic_new(
            host_name,
            port,
            bootstrap,
            socket_options,
            tls_connection_options,
            proxy_options,
            manual_window_management=manual_window_management,
            initial_window_size=initial_window_size,
            read_buffer_capacity=read_buffer_capacity)

    def request(self,
                request: 'HttpRequest',
                on_response: Optional[Callable[..., None]] = None,
                on_body: Optional[Callable[..., None]] = None) -> 'HttpClientStream':
        """Create :class:`HttpClientStream` to carry out the request/response exchange.

        NOTE: The HTTP stream sends no data until :meth:`HttpClientStream.activate()`
        is called. Call activate() when you're ready for callbacks and events to fire.

        Args:
            request (HttpRequest): Definition for outgoing request.

            on_response: Optional callback invoked once main response headers are received.
                The function should take the following arguments and return nothing:

                    *   `http_stream` (:class:`HttpClientStream`): HTTP stream carrying
                        out this request/response exchange.

                    *   `status_code` (int): Response status code.

                    *   `headers` (List[Tuple[str, str]]): Response headers as a
                        list of (name,value) pairs.

                    *   `**kwargs` (dict): Forward compatibility kwargs.

                An exception raise by this function will cause the HTTP stream to end in error.
                This callback is always invoked on the connection's event-loop thread.

            on_body: Optional callback invoked 0+ times as response body data is received.
                The function should take the following arguments and return nothing:

                    *   `http_stream` (:class:`HttpClientStream`): HTTP stream carrying
                        out this request/response exchange.

                    *   `chunk` (buffer): Response body data (not necessarily
                        a whole "chunk" of chunked encoding).

                    *   `**kwargs` (dict): Forward-compatibility kwargs.

                An exception raise by this function will cause the HTTP stream to end in error.
                This callback is always invoked on the connection's event-loop thread.

        Returns:
            HttpClientStream:
        """
        return HttpClientStream(self, request, on_response, on_body)

    def close(self) -> "concurrent.futures.Future":
        """Close the connection.

        Shutdown is asynchronous. This call has no effect if the connection is already
        closing.

        Returns:
            concurrent.futures.Future: This connection's :attr:`shutdown_future`,
            which completes when shutdown has finished.
        """
        _awscrt.http_connection_close(self._binding)
        return self.shutdown_future


class Http2ClientConnection(HttpClientConnectionBase):

    @classmethod
    def new(cls,
            host_name: str,
            port: int,
            bootstrap: Optional[ClientBootstrap] = None,
            socket_options: Optional[SocketOptions] = None,
            tls_connection_options: Optional[TlsConnectionOptions] = None,
            proxy_options: Optional['HttpProxyOptions'] = None,
            initial_settings: Optional[List[Http2Setting]] = None,
            on_remote_settings_changed: Optional[Callable[[List[Http2Setting]],
                                                          None]] = None,
            manual_window_management: bool = False,
            initial_window_size: Optional[int] = None,
            conn_manual_window_management: bool = False,
            conn_window_size_threshold: Optional[int] = None,
            stream_window_size_threshold: Optional[int] = None) -> "concurrent.futures.Future":
        """
        Asynchronously establish an HTTP/2 client connection.
        Notes: to set up the connection, the server must support HTTP/2 and TlsConnectionOptions

        This class extends HttpClientConnection with HTTP/2 specific functionality.

        HTTP/2 specific args:
            initial_settings (List[Http2Setting]): The initial settings to change for the connection.

            on_remote_settings_changed: Optional callback invoked once the remote peer changes its settings.
                And the settings are acknowledged by the local connection.
                The function should take the following arguments and return nothing:

                    *   `settings` (List[Http2Setting]): List of settings that were changed.

            manual_window_management (bool): If True, enables manual flow control window management.
                Default is False.

            initial_window_size (Optional[int]): Initial window size for flow control.
                Required if manual_window_management is True, ignored otherwise.

            conn_manual_window_management (bool): If True, enables manual connection-level flow control
                for the entire HTTP/2 connection. When enabled, the connection's flow-control window
                shrinks as body data is received across all streams. The initial connection window is
                65,535 bytes. When the window reaches 0, all streams stop receiving data until
                `update_window()` is called to increment the connection's window.
                Note: Padding in DATA frames counts against the window, but window updates for padding
                are sent automatically even in manual mode. Default is False.

            conn_window_size_threshold (Optional[int]): Threshold for sending connection-level WINDOW_UPDATE
                frames. Ignored if `conn_manual_window_management` is False. When the connection's window
                is above this threshold, WINDOW_UPDATE frames are batched. When it drops below, the update
                is sent. Default is 32,767 (half of the initial 65,535 window).

            stream_window_size_threshold (Optional[int]): Threshold for sending stream-level WINDOW_UPDATE
                frames. Ignored if `manual_window_management` is False. When a stream's window is above
                this threshold, WINDOW_UPDATE frames are batched. When it drops below, the update is sent.
                Default is half of `initial_window_size`.
        """
        return cls._generic_new(
            host_name,
            port,
            bootstrap,
            socket_options,
            tls_connection_options,
            proxy_options,
            HttpVersion.Http2,
            initial_settings,
            on_remote_settings_changed,
            manual_window_management=manual_window_management,
            initial_window_size=initial_window_size,
            conn_manual_window_management=conn_manual_window_management,
            conn_window_size_threshold=conn_window_size_threshold,
            stream_window_size_threshold=stream_window_size_threshold)

    def request(self,
                request: 'HttpRequest',
                on_response: Optional[Callable[..., None]] = None,
                on_body: Optional[Callable[..., None]] = None,
                manual_write: bool = False) -> 'Http2ClientStream':
        """Create `Http2ClientStream` to carry out the request/response exchange.

        NOTE: The HTTP stream sends no data until `Http2ClientStream.activate()`
        is called. Call activate() when you're ready for callbacks and events to fire.

        Args:
            request (HttpRequest): Definition for outgoing request.

            on_response: Optional callback invoked once main response headers are received.
                The function should take the following arguments and return nothing:

                    *   `http_stream` (`Http2ClientStream`): HTTP/2 stream carrying
                        out this request/response exchange.

                    *   `status_code` (int): Response status code.

                    *   `headers` (List[Tuple[str, str]]): Response headers as a
                        list of (name,value) pairs.

                    *   `**kwargs` (dict): Forward compatibility kwargs.

            on_body: Optional callback invoked 0+ times as response body data is received.
                The function should take the following arguments and return nothing:

                    *   `http_stream` (`Http2ClientStream`): HTTP/2 stream carrying
                        out this request/response exchange.

                    *   `chunk` (buffer): Response body data (not necessarily
                        a whole "chunk" of chunked encoding).

                    *   `**kwargs` (dict): Forward-compatibility kwargs.

            manual_write (bool): If True, enables manual data writing on the stream.
                This allows calling `write_data()` to stream the request body in chunks.
                Note: In the asyncio version, this is replaced by the async_body parameter.

        Returns:
            Http2ClientStream: Stream for the HTTP/2 request/response exchange.
        """
        return Http2ClientStream(self, request, on_response, on_body, manual_write)

    def close(self) -> "concurrent.futures.Future":
        """Close the connection.

        Shutdown is asynchronous. This call has no effect if the connection is already
        closing.

        Returns:
            concurrent.futures.Future: This connection's :attr:`shutdown_future`,
            which completes when shutdown has finished.
        """
        _awscrt.http_connection_close(self._binding)
        return self.shutdown_future

    def update_window(self, increment_size: int) -> None:
        """
        Update the connection's flow control window.

        Args:
            increment_size (int): Number of bytes to increment the window by.
        """
        _awscrt.http2_connection_update_window(self._binding, increment_size)


class HttpStreamBase(NativeResource):
    """Base for HTTP stream classes.

    Attributes:
        connection: The HTTP connection this stream belongs to.
        completion_future: Future that completes when the operation finishes.
    """
    __slots__ = ('_connection', '_completion_future', '_on_body_cb')

    def __init__(self, connection, on_body: Optional[Callable[..., None]] = None) -> None:
        super().__init__()
        self._connection = connection
        self._completion_future = Future()
        self._on_body_cb: Optional[Callable[..., None]] = on_body

    @property
    def connection(self) -> HttpConnectionBase:
        return self._connection

    @property
    def completion_future(self) -> "concurrent.futures.Future":
        return self._completion_future

    def _on_body(self, chunk: bytes) -> None:
        if self._on_body_cb:
            self._on_body_cb(http_stream=self, chunk=chunk)


class HttpClientStreamBase(HttpStreamBase):
    """Base for HTTP client stream classes.

    Attributes:
        connection: This stream's connection.

        completion_future: Future that completes when
            the request/response exchange is finished.
    """

    __slots__ = ('_response_status_code', '_on_response_cb', '_on_body_cb', '_request', '_version')

    def _init_common(self,
                     connection: HttpClientConnectionBase,
                     request: 'HttpRequest',
                     on_response: Optional[Callable[..., None]] = None,
                     on_body: Optional[Callable[..., None]] = None,
                     http2_manual_write: bool = False) -> None:
        assert isinstance(connection, HttpClientConnectionBase)
        assert isinstance(request, HttpRequest)
        assert callable(on_response) or on_response is None
        assert callable(on_body) or on_body is None

        super().__init__(connection, on_body)

        self._on_response_cb: Optional[Callable[..., None]] = on_response
        self._response_status_code: Optional[int] = None

        # keep HttpRequest alive until stream completes
        self._request = request
        self._version = connection.version
        self._binding = _awscrt.http_client_stream_new(self, connection, request, http2_manual_write)

    @property
    def version(self) -> HttpVersion:
        """HttpVersion: Protocol used by this stream"""
        return self._version

    @property
    def response_status_code(self) -> Optional[int]:
        """int: The response status code.

        This is None until a response arrives."""
        return self._response_status_code

    def _on_response(self, status_code: int, name_value_pairs: List[Tuple[str, str]]) -> None:
        self._response_status_code = status_code

        if self._on_response_cb:
            self._on_response_cb(http_stream=self, status_code=status_code, headers=name_value_pairs)

    def _on_complete(self, error_code: int) -> None:
        # done with HttpRequest, drop reference
        self._request = None  # type: ignore

        if error_code == 0:
            self._completion_future.set_result(self._response_status_code)
        else:
            self._completion_future.set_exception(awscrt.exceptions.from_code(error_code))

    def update_window(self, increment_size: int) -> None:
        """
        Update the stream's flow control window.

        Args:
            increment_size (int): Number of bytes to increment the window by.
        """
        _awscrt.http_stream_update_window(self, increment_size)


class HttpClientStream(HttpClientStreamBase):
    """HTTP stream that sends a request and receives a response.

    Create an HttpClientStream with :meth:`HttpClientConnection.request()`.

    NOTE: The HTTP stream sends no data until :meth:`HttpClientStream.activate()`
    is called. Call activate() when you're ready for callbacks and events to fire.

    Attributes:
        connection (HttpClientConnection): This stream's connection.

        completion_future (concurrent.futures.Future): Future that will contain
            the response status code (int) when the request/response exchange
            completes. If the exchange fails to complete, the Future will
            contain an exception indicating why it failed.
    """

    def __init__(self,
                 connection: HttpClientConnection,
                 request: 'HttpRequest',
                 on_response: Optional[Callable[..., None]] = None,
                 on_body: Optional[Callable[..., None]] = None) -> None:
        self._init_common(connection, request, on_response, on_body)

    def activate(self) -> None:
        """Begin sending the request.

        The HTTP stream does nothing until this is called. Call activate() when you
        are ready for its callbacks and events to fire.
        """
        _awscrt.http_client_stream_activate(self)


class Http2ClientStream(HttpClientStreamBase):
    def __init__(self,
                 connection: HttpClientConnection,
                 request: 'HttpRequest',
                 on_response: Optional[Callable[..., None]] = None,
                 on_body: Optional[Callable[..., None]] = None,
                 manual_write: bool = False) -> None:
        self._init_common(connection, request, on_response, on_body, manual_write)

    def activate(self) -> None:
        """Begin sending the request.

        The HTTP stream does nothing until this is called. Call activate() when you
        are ready for its callbacks and events to fire.
        """
        _awscrt.http_client_stream_activate(self)

    def write_data(self,
                   data_stream: Union[InputStream, Any],
                   end_stream: bool = False) -> "concurrent.futures.Future":
        """Write a chunk of data to the request body stream.

        This method is only available when the stream was created with
        manual_write=True. This allows incremental writing of request data.

        Note: In the asyncio version, this is replaced by the request_body_generator parameter
        which accepts an async generator.

        Args:
            data_stream (Union[InputStream, Any]): Data to write. If not an InputStream,
                it will be wrapped in one. Can be None to send an empty chunk.

            end_stream (bool): True to indicate this is the last chunk and no more data
                will be sent. False if more chunks will follow.

        Returns:
            concurrent.futures.Future: Future that completes when the write operation
                is done. The future will contain None on success, or an exception on failure.
        """
        future = Future()
        body_stream = InputStream.wrap(data_stream, allow_none=True)

        def on_write_complete(error_code: int) -> None:
            if future.cancelled():
                # the future was cancelled, so we don't need to set the result or exception
                return
            if error_code:
                future.set_exception(awscrt.exceptions.from_code(error_code))
            else:
                future.set_result(None)

        _awscrt.http2_client_stream_write_data(self, body_stream, end_stream, on_write_complete)
        return future


class HttpMessageBase(NativeResource):
    """
    Base for HttpRequest and HttpResponse classes.
    """
    __slots__ = ('_headers', '_body_stream')

    def __init__(self, binding: Any, headers: 'HttpHeaders',
                 body_stream: Optional[Union[InputStream, Any]] = None) -> None:
        assert isinstance(headers, HttpHeaders)

        super().__init__()
        self._binding = binding
        self._headers = headers
        self._body_stream: Optional[InputStream] = None

        if body_stream:
            self.body_stream = body_stream

    @property
    def headers(self) -> 'HttpHeaders':
        """HttpHeaders: Headers to send."""
        return self._headers

    @property
    def body_stream(self) -> Optional[InputStream]:
        return self._body_stream

    @body_stream.setter
    def body_stream(self, stream: Union[InputStream, Any]) -> None:
        self._body_stream = InputStream.wrap(stream)
        _awscrt.http_message_set_body_stream(self._binding, self._body_stream)


class HttpRequest(HttpMessageBase):
    """
    Definition for an outgoing HTTP request.

    The request may be transformed (ex: signing the request) before its data is eventually sent.

    Args:
        method (str): HTTP request method (verb). Default value is "GET".
        path (str): HTTP path-and-query value. Default value is "/".
        headers (Optional[HttpHeaders]): Optional headers. If None specified,
            an empty :class:`HttpHeaders` is created.
        body_stream(Optional[Union[InputStream, io.IOBase]]): Optional body as binary stream.
    """

    __slots__ = ()

    def __init__(self,
                 method: str = 'GET',
                 path: str = '/',
                 headers: Optional['HttpHeaders'] = None,
                 body_stream: Optional[Union[InputStream, Any]] = None) -> None:
        assert isinstance(headers, HttpHeaders) or headers is None

        if headers is None:
            headers = HttpHeaders()

        binding = _awscrt.http_message_new_request(headers)
        super().__init__(binding, headers, body_stream)
        self.method = method
        self.path = path

    @classmethod
    def _from_bindings(cls, request_binding: Any, headers_binding: Any) -> 'HttpRequest':
        """Construct HttpRequest and its HttpHeaders from pre-existing native objects"""

        # avoid class's default constructor
        # just invoke parent class's __init__()
        request = cls.__new__(cls)
        headers = HttpHeaders._from_binding(headers_binding)
        super(cls, request).__init__(request_binding, headers)
        return request

    @property
    def method(self) -> str:
        """str: HTTP request method (verb)."""
        return _awscrt.http_message_get_request_method(self._binding)

    @method.setter
    def method(self, method: str) -> None:
        _awscrt.http_message_set_request_method(self._binding, method)

    @property
    def path(self) -> str:
        """str: HTTP path-and-query value."""
        return _awscrt.http_message_get_request_path(self._binding)

    @path.setter
    def path(self, path: str) -> None:
        return _awscrt.http_message_set_request_path(self._binding, path)


class HttpHeaders(NativeResource):
    """
    Collection of HTTP headers.

    A given header name may have multiple values.
    Header names are always treated in a case-insensitive manner.
    HttpHeaders can be iterated over as (name,value) pairs.

    Args:
        name_value_pairs (Optional[List[Tuple[str, str]]]): Construct from a
            collection of (name,value) pairs.
    """

    __slots__ = ()

    def __init__(self, name_value_pairs: Optional[List[Tuple[str, str]]] = None) -> None:
        super().__init__()
        self._binding = _awscrt.http_headers_new()
        if name_value_pairs:
            self.add_pairs(name_value_pairs)

    @classmethod
    def _from_binding(cls, binding: Any) -> 'HttpHeaders':
        """Construct from a pre-existing native object"""
        headers = cls.__new__(cls)  # avoid class's default constructor
        super(cls, headers).__init__()  # just invoke parent class's __init__()
        headers._binding = binding
        return headers

    def add(self, name: str, value: str) -> None:
        """
        Add a name-value pair.

        Args:
            name (str): Name.
            value (str): Value.
        """
        assert isinstance(name, str)
        assert isinstance(value, str)
        _awscrt.http_headers_add(self._binding, name, value)

    def add_pairs(self, name_value_pairs: List[Tuple[str, str]]) -> None:
        """
        Add list of (name,value) pairs.

        Args:
            name_value_pairs (List[Tuple[str, str]]): List of (name,value) pairs.
        """
        _awscrt.http_headers_add_pairs(self._binding, name_value_pairs)

    def set(self, name: str, value: str) -> None:
        """
        Set a name-value pair, any existing values for the name are removed.

        Args:
            name (str): Name.
            value (str): Value.
        """
        assert isinstance(name, str)
        assert isinstance(value, str)
        _awscrt.http_headers_set(self._binding, name, value)

    def get_values(self, name: str) -> Iterator[str]:
        """
        Return an iterator over the values for this name.

        Args:
            name (str): Name.

        Returns:
            Iterator[str]: Iterator over values for this header name
        """
        assert isinstance(name, str)
        name = name.lower()
        for i in range(_awscrt.http_headers_count(self._binding)):
            name_i, value_i = _awscrt.http_headers_get_index(self._binding, i)
            if name_i.lower() == name:
                yield value_i

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get the first value for this name, ignoring any additional values.
        Returns `default` if no values exist.

        Args:
            name (str): Name.
            default (Optional[str]): If `name` not found, this value is returned.
                Defaults to None.
        Returns:
            Optional[str]: Header value or default
        """
        assert isinstance(name, str)
        return _awscrt.http_headers_get(self._binding, name, default)

    def remove(self, name: str) -> None:
        """
        Remove all values for this name.
        Raises a KeyError if name not found.

        Args:
            name (str): Header name.
        """
        assert isinstance(name, str)
        _awscrt.http_headers_remove(self._binding, name)

    def remove_value(self, name: str, value: str) -> None:
        """
        Remove a specific value for this name.
        Raises a ValueError if value not found.

        Args:
            name (str): Name.
            value (str): Value.
        """
        assert isinstance(name, str)
        assert isinstance(value, str)
        _awscrt.http_headers_remove_value(self._binding, name, value)

    def clear(self) -> None:
        """
        Clear all headers.
        """
        _awscrt.http_headers_clear(self._binding)

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        """
        Iterate over all (name,value) pairs.
        """
        for i in range(_awscrt.http_headers_count(self._binding)):
            yield _awscrt.http_headers_get_index(self._binding, i)

    def __str__(self) -> str:
        return self.__class__.__name__ + "(" + str([pair for pair in self]) + ")"


class HttpProxyConnectionType(IntEnum):
    """Proxy connection type enumeration"""
    Legacy = 0
    """
    Use the old connection establishment logic that would use:

         1. Forwarding if not using TLS
         2. Tunneling if using TLS
    """

    Forwarding = 1
    """
    Establish a request forwarding connection to the proxy.

    In this case, TLS is not a valid option.
    """

    Tunneling = 2
    """Establish a tunneling connection through the proxy to the ultimate endpoint."""


class HttpProxyAuthenticationType(IntEnum):
    """Proxy authentication type enumeration."""
    Nothing = 0
    """No authentication"""

    Basic = 1
    """Username and password"""


class HttpProxyOptions:
    """
    Proxy options for HTTP clients.

    Args:
        host_name (str): Name of the proxy server to connect through.

        port (int): Port number of the proxy server to connect through.

        tls_connection_options (Optional[TlsConnectionOptions]): Optional
            `TlsConnectionOptions` for the Local to Proxy connection.
            Must be distinct from the `TlsConnectionOptions`
            provided to the HTTP connection.

        auth_type (HttpProxyAuthenticationType): Type of proxy authentication to use.
            Default is :const:`HttpProxyAuthenticationType.Nothing`.

        auth_username (Optional[str]): Username to use when `auth_type` is
            :const:`HttpProxyAuthenticationType.Basic`.

        auth_password (Optional[str]): Username to use when `auth_type` is
            :const:`HttpProxyAuthenticationType.Basic`.

        connection_type (Optional[HttpProxyConnectionType): Type of proxy connection to make.
            Default is :const:`HttpProxyConnectionType.Legacy`.


    Attributes:
        host_name (str): Name of the proxy server to connect through.

        port (int): Port number of the proxy server to connect through.

        tls_connection_options (Optional[TlsConnectionOptions]): Optional
            `TlsConnectionOptions` for the Local to Proxy connection.
            Must be distinct from the `TlsConnectionOptions`
            provided to the HTTP connection.

        auth_type (HttpProxyAuthenticationType): Type of proxy authentication to use.

        auth_username (Optional[str]): Username to use when `auth_type` is
            :const:`HttpProxyAuthenticationType.Basic`.

        auth_password (Optional[str]): Username to use when `auth_type` is
            :const:`HttpProxyAuthenticationType.Basic`.

        connection_type (HttpProxyConnectionType): Type of proxy connection to make.

    """

    def __init__(self,
                 host_name: str,
                 port: int,
                 tls_connection_options: Optional[TlsConnectionOptions] = None,
                 auth_type: HttpProxyAuthenticationType = HttpProxyAuthenticationType.Nothing,
                 auth_username: Optional[str] = None,
                 auth_password: Optional[str] = None,
                 connection_type: HttpProxyConnectionType = HttpProxyConnectionType.Legacy) -> None:
        self.host_name = host_name
        self.port = port
        self.tls_connection_options = tls_connection_options
        self.auth_type = auth_type
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.connection_type = connection_type


class _HttpClientConnectionCore:
    '''
    Private class to keep all the related Python object alive until C land clean up for HttpClientConnection
    '''

    def __init__(
            self,
            host_name: str,
            port: int,
            bootstrap: Optional[ClientBootstrap] = None,
            tls_connection_options: Optional[TlsConnectionOptions] = None,
            connect_future: Optional[Future] = None,
            expected_version: Optional[HttpVersion] = None,
            on_remote_settings_changed: Optional[Callable[[List[Http2Setting]], None]] = None,
            asyncio_connection=False) -> None:
        self._shutdown_future = None
        self._host_name = host_name
        self._port = port
        self._bootstrap = bootstrap
        self._tls_connection_options = tls_connection_options
        self._connect_future = connect_future
        self._expected_version = expected_version
        self._on_remote_settings_changed_from_user = on_remote_settings_changed
        self._asyncio_connection = asyncio_connection

    def _on_connection_setup(self, binding: Any, error_code: int, http_version: HttpVersion) -> None:
        if self._connect_future is None:
            return
        if error_code != 0:
            self._connect_future.set_exception(awscrt.exceptions.from_code(error_code))
            return
        if self._expected_version and self._expected_version != http_version:
            # unexpected protocol version
            # AWS_ERROR_HTTP_UNSUPPORTED_PROTOCOL
            self._connect_future.set_exception(awscrt.exceptions.from_code(2060))
            return
        if self._asyncio_connection:
            # Import is done here to avoid circular import issues
            from awscrt.aio.http import AIOHttpClientConnection, AIOHttp2ClientConnection
            if http_version == HttpVersion.Http2:
                connection = AIOHttp2ClientConnection()
            else:
                connection = AIOHttpClientConnection()
        else:
            if http_version == HttpVersion.Http2:
                connection = Http2ClientConnection()
            else:
                connection = HttpClientConnection()

        connection._host_name = self._host_name
        connection._port = self._port

        connection._binding = binding
        connection._version = HttpVersion(http_version)
        self._shutdown_future = connection.shutdown_future
        self._connect_future.set_result(connection)
        # release reference to the future, as it points to connection which creates a cycle reference.
        self._connect_future = None

    def _on_shutdown(self, error_code: int) -> None:
        if self._shutdown_future is None:
            # connection failed, ignore shutdown
            return
        if error_code:
            self._shutdown_future.set_exception(awscrt.exceptions.from_code(error_code))
        else:
            self._shutdown_future.set_result(None)

    def _on_remote_settings_changed(self, native_settings: List[Tuple[int, int]]) -> None:
        if self._on_remote_settings_changed_from_user:
            # convert the list of tuple to list of Http2Setting
            settings = [Http2Setting(Http2SettingID(id), value) for id, value in native_settings]
            self._on_remote_settings_changed_from_user(settings)
