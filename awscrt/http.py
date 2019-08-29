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
from enum import IntEnum
from awscrt import NativeResource
from awscrt.io import ClientBootstrap, TlsConnectionOptions, SocketOptions

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
    __slots__ = ()

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


    def make_request(self, method, uri_str, outgoing_headers, on_outgoing_body, on_incoming_body):
        """
        path_and_query is the path and query portion
        of a URL. method is the http method (GET, PUT, etc...). outgoing_headers are the headers to send as part
        of the request.

        on_read_body is invoked to read the body of the request. It takes a single parameter of type MemoryView
        (it's writable), and you signal the end of the stream by returning OutgoingHttpBodyState.Done for the first tuple
        argument. If you aren't done sending the body, the first tuple argument should be OutgoingHttpBodyState.InProgress
        The second tuple argument is the size of the data written to the memoryview.

        on_incoming_body is invoked as the response body is received. It takes a single argument of type bytes.

        Makes an Http request. When the headers from the response are received, the returned
        HttpRequest.response_headers_received future will have a result.
        and request.response_headers will be filled in, and request.response_code will be available.
        After this future completes, you can get the result of request.response_completed,
        for the remainder of the response.
        """
        request = HttpRequest(self, method, uri_str, outgoing_headers, on_outgoing_body, on_incoming_body)

        def on_stream_completed(error_code):
            if error_code == 0:
                request.response_completed.set_result(error_code)
            else:
                request.response_completed.set_exception(Exception(error_code))

        def on_incoming_headers_received(headers, response_code, has_body):
            request.response_headers = headers
            request.response_code = response_code
            request.has_response_body = has_body
            request.response_headers_received.set_result(response_code)

        try:
            request._stream = _awscrt.http_client_stream_new(
                self,
                request,
                on_stream_completed,
                on_incoming_headers_received)

        except Exception as e:
            request.response_completed.set_exception(e)

        return request


class OutgoingHttpBodyState(IntEnum):
    InProgress = 0
    Done = 1


class HttpRequest(object):
    """
    Represents an HttpRequest to pass to HttpClientConnection.make_request(). path_and_query is the path and query portion
    of a URL. method is the http method (GET, PUT, etc...). outgoing_headers are the headers to send as part
    of the request.

    on_read_body is invoked to read the body of the request. It takes a single parameter of type MemoryView
    (it's writable), and you signal the end of the stream by returning OutgoingHttpBodyState.Done for the first tuple
    argument. If you aren't done sending the body, the first tuple argument should be OutgoingHttpBodyState.InProgress
    The second tuple argument is the size of the data written to the memoryview.

    on_incoming_body is invoked as the response body is received. It takes a single argument of type bytes.
    """
    __slots__ = ('_connection', 'path_and_query', 'method', 'outgoing_headers', '_on_read_body', '_on_incoming_body', '_stream',
                 'response_headers', 'response_code', 'has_response_body', 'response_headers_received',
                 'response_completed')

    def __init__(self, connection, method, path_and_query, outgoing_headers, on_read_body, on_incoming_body):
        assert method is not None
        assert outgoing_headers is not None
        assert connection is not None and isinstance(connection, HttpClientConnection)

        self.path_and_query = path_and_query

        if path_and_query is None:
            self.path_and_query = '/'

        self._connection = connection
        self.method = method
        self.outgoing_headers = outgoing_headers
        self._on_read_body = on_read_body
        self._on_incoming_body = on_incoming_body
        self.response_completed = Future()
        self.response_headers_received = Future()
        self._stream = None
        self.response_headers = None
        self.response_code = None
        self.has_response_body = False
