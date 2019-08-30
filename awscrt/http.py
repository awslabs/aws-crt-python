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

import _awscrt
from concurrent.futures import Future
from collections import defaultdict
from enum import IntEnum, Enum
from awscrt import NativeResource
from awscrt.io import ClientBootstrap, TlsConnectionOptions, SocketOptions

class HttpMethod(Enum):
    GET = 1
    HEAD = 2
    POST = 3
    PUT = 4
    DELETE = 5
    CONNECT = 6
    OPTIONS = 7
    TRACE = 8
    PATCH = 9


class HttpConnection(NativeResource):
    """
    Base for HTTP connection classes. Do not instantiate directly.
    """

    __slots__ = ('_shutdown_future')

    def __init__(self):
        assert not type(self) is HttpConnection # Do not instantiate base class directly
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


class HttpClientConnection(HttpConnection):
    """
    An HTTP client connection. All operations are async.
    Use HttpClientConnection.new() to establish a new connection.
    """
    __slots__ = ('host_name', 'port')

    @classmethod
    def new(cls, bootstrap, host_name, port, socket_options,
                on_connection_shutdown=None, tls_connection_options=None):
        """
        Initiates a new connection to host_name and port using socket_options and tls_connection_options if supplied.
        if tls_connection_options is None, then the connection will be attempted over plain-text.

        Returns a future where the result is a new instance to HttpClientConnection, once the connection has completed
        and is ready for use.
        """
        future = Future()
        try:
            assert isinstance(bootstrap, ClientBootstrap)
            assert host_name
            assert tls_connection_options is None or isinstance(tls_connection_options, TlsConnectionOptions)
            assert isinstance(socket_options, SocketOptions)

            connection = cls()
            connection.host_name = host_name
            connection.port = port

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


    def make_request(self, request, on_response, on_body):
        return HttpClientStream(self, request, on_response, on_body)


class HttpStream(NativeResource):
    __slots__ = ('connection', 'complete_future', '_on_body_cb')

    def __init__(self, connection, on_body=None):
        self.connection = connection
        self.complete_future = Future()
        self._on_body_cb = on_body

    def _on_body(self, chunk):
        if self._on_body_cb:
            self._on_body_cb(self, chunk)

    def _on_complete(self, error_code):
        if error_code:
            self.complete_future.set_result(None)
        else:
            self.complete_future.set_exception(Exception(error_code)) # TODO: Actual exceptions for error_codes


class HttpClientStream(HttpStream):
    __slots__ = ('request', 'response_status_code', '_on_response_cb', '_on_body_cb')

    def __init__(self, connection, request, on_response=None, on_body=None):
        assert isinstance(connection, HttpClientConnection)
        assert isinstance(request, HttpRequest)
        assert callable(on_response) or on_response is None
        assert callable(on_body) or on_body is None

        super(HttpStream, self).__init__(connection, on_body)

        self.request = request
        self._on_response_cb = on_response
        self.response_status_code = None

        _awscrt.http_client_stream_new(self, connection, request)


    def _on_response(self, status_code, name_value_pairs):
        self.response_status_code = status_code

        headers = HttpHeaders()
        for pair in name_value_pairs:
            headers.add(pair[0], pair[1])

        if self._on_response_cb:
            self._on_response_cb(self, status_code, headers)


class HttpRequest(object):
    __slots__ = ('method', 'path', 'headers', 'body')

    def __init__(self, method=None, path=None, body=None):
        self.method = method
        self.path = path
        self.body = body
        self.headers = HttpHeaders()


class HttpHeaders(object):
    __slots__ = ('map')
    def __init__(self):
        self.map = defaultdict(list)

    def add(self, name, value):
        self.map[name.lower()].append(value)

    def set(self, name, value):
        self.map[name.lower()] = [value]

    def get_list(self, name):
        return self.map.get(name.lower(), [])

    def get(self, name):
        values = self.map.get(name.lower())
        if values:
            return values[0]
        else:
            return ""

    def remove(self, name):
        try:
            del self.map[name.lower()]
        except:
            pass

