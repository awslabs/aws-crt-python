# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

from __future__ import absolute_import
import _awscrt
from concurrent.futures import Future
from collections import defaultdict
from awscrt import NativeResource, isinstance_str
from awscrt.io import ClientBootstrap, EventLoopGroup, DefaultHostResolver, InputStream, TlsConnectionOptions, SocketOptions


class HttpConnectionBase(NativeResource):
    """
    Base for HTTP connection classes.
    """

    __slots__ = ('_shutdown_future')

    def __init__(self):
        super(HttpConnectionBase, self).__init__()
        self._shutdown_future = Future()

    def close(self):
        """
        Close the connection.
        Returns a future which will have a result when the connection has finished shutting down.
        The result will an int indicating why shutdown occurred.
        """
        _awscrt.http_connection_close(self._binding)
        return self._shutdown_future

    def add_shutdown_callback(self, fn):
        """
        fn(error_code: int) will be called when the connection shuts down.
        error_code indicates the reason that shutdown occurred.
        Note that the connection may have been garbage collected by the time fn is finally called.
        """
        self._shutdown_future.add_done_callback(lambda future: fn(future.result()))

    def is_open(self):
        """
        Returns True if the connection is open and usable, False otherwise.
        """
        return _awscrt.http_connection_is_open(self._binding)


class HttpClientConnection(HttpConnectionBase):
    """
    An HTTP client connection. All operations are async.
    Use HttpClientConnection.new() to establish a new connection.
    """
    __slots__ = ('_host_name', '_port')

    @classmethod
    def new(cls, host_name, port, socket_options=SocketOptions(), tls_connection_options=None, bootstrap=None):
        """
        Initiates a new connection to host_name and port using socket_options and tls_connection_options if supplied.
        if tls_connection_options is None, then the connection will be attempted over plain-text.

        Returns a future where the result is a new instance to HttpClientConnection, once the connection has completed
        and is ready for use.
        """
        future = Future()
        try:
            assert isinstance(bootstrap, ClientBootstrap) or bootstrap is None
            assert isinstance_str(host_name)
            assert isinstance(tls_connection_options, TlsConnectionOptions) or tls_connection_options is None
            assert isinstance(socket_options, SocketOptions)

            if not bootstrap:
                event_loop_group = EventLoopGroup(1)
                host_resolver = DefaultHostResolver(event_loop_group)
                bootstrap = ClientBootstrap(event_loop_group, host_resolver)

            connection = cls()
            connection._host_name = host_name
            connection._port = port

            def on_connection_setup(binding, error_code):
                if error_code == 0:
                    connection._binding = binding
                    future.set_result(connection)
                else:
                    future.set_exception(Exception("Error during connect: err={}".format(error_code)))

            _awscrt.http_client_connection_new(
                bootstrap,
                on_connection_setup,
                connection._shutdown_future,
                host_name,
                port,
                socket_options,
                tls_connection_options)

        except Exception as e:
            future.set_exception(e)

        return future

    @property
    def host_name(self):
        return self._host_name

    @property
    def port(self):
        return self._port

    def request(self, request, on_response=None, on_body=None):
        return HttpClientStream(self, request, on_response, on_body)


class HttpStreamBase(NativeResource):
    __slots__ = ('_connection', '_completion_future', '_on_body_cb')

    def __init__(self, connection, on_body=None):
        super(HttpStreamBase, self).__init__()
        self._connection = connection
        self._completion_future = Future()
        self._on_body_cb = on_body

    @property
    def connection(self):
        return self._connection

    @property
    def completion_future(self):
        return self._completion_future

    def _on_body(self, chunk):
        if self._on_body_cb:
            self._on_body_cb(self, chunk)


class HttpClientStream(HttpStreamBase):
    __slots__ = ('_response_status_code', '_on_response_cb', '_on_body_cb')

    def __init__(self, connection, request, on_response=None, on_body=None):
        assert isinstance(connection, HttpClientConnection)
        assert isinstance(request, HttpRequest)
        assert callable(on_response) or on_response is None
        assert callable(on_body) or on_body is None

        super(HttpClientStream, self).__init__(connection, on_body)

        self._on_response_cb = on_response
        self._response_status_code = None

        _awscrt.http_client_stream_new(self, connection, request)

    @property
    def response_status_code(self):
        return self._response_status_code

    def _on_response(self, status_code, name_value_pairs):
        self._response_status_code = status_code

        if self._on_response_cb:
            self._on_response_cb(self, status_code, name_value_pairs)

    def _on_complete(self, error_code):
        if error_code == 0:
            self._completion_future.set_result(self._response_status_code)
        else:
            self._completion_future.set_exception(Exception(error_code))  # TODO: Actual exceptions for error_codes


class HttpMessageBase(NativeResource):
    """
    Base for HttpRequest and HttpResponse classes.
    """
    __slots__ = ('_headers')

    def __init__(self, binding, headers_binding, headers=None, body_stream=None):
        super(HttpMessageBase, self).__init__()
        self._binding = binding
        self._headers = HttpHeaders._from_binding(headers_binding)
        if headers:
            self.headers.add_pairs(headers)

        if body_stream:
            self.body_stream = body_stream

    @property
    def headers(self):
        return self._headers

    @property
    def body_stream(self):
        return _awscrt.http_message_get_body_stream(self._binding)

    @body_stream.setter
    def body_stream(self, stream):
        stream = InputStream.wrap(stream)
        return _awscrt.http_message_set_body_stream(self._binding, stream)


class HttpRequest(HttpMessageBase):
    """
    Definition for an outgoing HTTP request.
    The request may be transformed (ex: signing the request) before its data is eventually sent.
    """

    __slots__ = ()

    def __init__(self, method='GET', path='/', headers=None, body_stream=None):
        binding, headers_binding = _awscrt.http_message_new_request()
        super(HttpRequest, self).__init__(binding, headers_binding, headers, body_stream)
        self.method = method
        self.path = path

    @property
    def method(self):
        return _awscrt.http_message_get_request_method(self._binding)

    @method.setter
    def method(self, method):
        _awscrt.http_message_set_request_method(self._binding, method)

    @property
    def path(self):
        return _awscrt.http_message_get_request_path(self._binding)

    @path.setter
    def path(self, path):
        return _awscrt.http_message_set_request_path(self._binding, path)


class HttpHeaders(NativeResource):
    """
    Collection of HTTP headers.
    A given header name may have multiple values.
    Header names are always treated in a case-insensitive manner.
    HttpHeaders can be iterated over as (name,value) pairs.
    """

    __slots__ = ()

    def __init__(self, name_value_pairs=None):
        """
        Construct from a collection of (name,value) pairs.
        """
        super(HttpHeaders, self).__init__()
        self._binding = _awscrt.http_headers_new()
        if name_value_pairs:
            self.add_pairs(name_value_pairs)

    @classmethod
    def _from_binding(cls, binding):
        """Construct from a pre-existing native object"""
        headers = cls.__new__(cls)  # avoid class's default __init__()
        super(cls, headers).__init__()  # just invoke parent class's __init__()
        headers._binding = binding
        return headers

    def add(self, name, value):
        """
        Add a name-value pair.
        """
        assert isinstance_str(name)
        assert isinstance_str(value)
        _awscrt.http_headers_add(self._binding, name, value)

    def add_pairs(self, name_value_pairs):
        """
        Add list of (name,value) pairs.
        """
        _awscrt.http_headers_add_pairs(self._binding, name_value_pairs)

    def set(self, name, value):
        """
        Set a name-value pair, any existing values for the name are removed.
        """
        assert isinstance_str(name)
        assert isinstance_str(value)
        _awscrt.http_headers_set(self._binding, name, value)

    def get_values(self, name):
        """
        Return an iterator over the values for this name.
        """
        assert isinstance_str(name)
        name = name.lower()
        for i in range(_awscrt.http_headers_count(self._binding)):
            name_i, value_i = _awscrt.http_headers_get_index(self._binding, i)
            if name_i.lower() == name:
                yield value_i

    def get(self, name, default=None):
        """
        Get the first value for this name, ignoring any additional values.
        Returns `default` if no values exist.
        """
        assert isinstance_str(name)
        return _awscrt.http_headers_get(self._binding, name, default)

    def remove(self, name):
        """
        Remove all values for this name.
        Raises a KeyError if name not found.
        """
        assert isinstance_str(name)
        _awscrt.http_headers_remove(self._binding, name)

    def remove_value(self, name, value):
        """
        Remove a specific value for this name.
        Raises a ValueError if value not found.
        """
        assert isinstance_str(name)
        assert isinstance_str(value)
        _awscrt.http_headers_remove_value(self._binding, name, value)

    def clear(self):
        """
        Clear all headers
        """
        _awscrt.http_headers_clear(self._binding)

    def __iter__(self):
        """
        Iterate over all (name,value) pairs.
        """
        for i in range(_awscrt.http_headers_count(self._binding)):
            yield _awscrt.http_headers_get_index(self._binding, i)

    def __str__(self):
        return self.__class__.__name__ + "(" + str([pair for pair in self]) + ")"
