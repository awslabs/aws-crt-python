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
from io import IOBase
from awscrt import NativeResource, isinstance_str
from awscrt.io import ClientBootstrap, EventLoopGroup, DefaultHostResolver, TlsConnectionOptions, SocketOptions


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
    __slots__ = ('_headers', '_body_stream')

    def __init__(self, headers=None, body_stream=None):
        assert isinstance(body_stream, IOBase) or body_stream is None

        super(HttpMessageBase, self).__init__()
        self._headers = HttpHeaders(headers)
        self._body_stream = body_stream

    @property
    def headers(self):
        return self._headers

    @property
    def body_stream(self):
        return self._body_stream


class HttpRequest(HttpMessageBase):
    """
    Definition for an outgoing HTTP request.
    The request may be transformed (ex: signing the request) before its data is eventually sent.
    """

    __slots__ = ('method', 'path')

    def __init__(self, method='GET', path='/', headers=None, body_stream=None):
        super(HttpRequest, self).__init__(headers, body_stream)
        self.method = method
        self.path = path
        self._binding = _awscrt.http_request_new(self, self._body_stream)


class HttpHeaders(object):
    """
    Collection of HTTP headers.
    A given header name may have multiple values.
    Header names are always treated in a case-insensitive manner.
    HttpHeaders can be iterated over as (name,value) pairs.
    """

    __slots__ = ('_map')

    def __init__(self, name_value_pairs=None):
        """
        Construct from a collection of (name,value) pairs.
        """
        self._map = defaultdict(list)
        if name_value_pairs:
            self.add_pairs(name_value_pairs)

    def add(self, name, value):
        """
        Add a name-value pair.
        """
        assert isinstance_str(name)
        assert isinstance_str(value)
        self._map[name.lower()].append((name, value))

    def add_pairs(self, name_value_pairs):
        """
        Add list of (name,value) pairs.
        """
        for pair in name_value_pairs:
            assert len(pair) == 2
            self.add(pair[0], pair[1])

    def set(self, name, value):
        """
        Set a name-value pair, any existing values for the name are removed.
        """
        assert isinstance_str(name)
        assert isinstance_str(value)
        self._map[name.lower()] = [(name, value)]

    def get_values(self, name):
        """
        Get the list of values for this name.
        Returns an empty list if no values exist.
        """
        values = self._map.get(name.lower())
        if values:
            return [pair[1] for pair in values]
        return []

    def get(self, name, default=None):
        """
        Get the first value for this name, ignoring any additional values.
        Returns `default` if no values exist.
        """
        values = self._map.get(name.lower())
        if values:
            return values[0][1]
        return default

    def remove(self, name):
        """
        Remove all values for this name.
        Raises a KeyError if name not found.
        """
        del self._map[name.lower()]

    def remove_value(self, name, value):
        """
        Remove a specific value for this name.
        Raises a ValueError if value not found.
        """
        lower_name = name.lower()
        values = self._map[lower_name]
        if values:
            for i, pair in enumerate(values):
                if pair[1] == value:
                    if len(values) == 1:
                        del self._map[lower_name]
                    else:
                        del values[i]
                    return
        raise ValueError("HttpHeaders.remove_value(name,value): value not found")

    def clear(self):
        """
        Clear all headers
        """
        self._map.clear()

    def __iter__(self):
        """
        Iterate over all (name,value) pairs.
        """
        for values in self._map.values():
            for pair in values:
                yield pair

    def __str__(self):
        return self.__class__.__name__ + "(" + str([pair for pair in self]) + ")"
