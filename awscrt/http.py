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

import _aws_crt_python
from concurrent.futures import Future
from enum import IntEnum
from awscrt.io import ClientBootstrap, TlsConnectionOptions, SocketOptions


class HttpClientConnection(object):
    """
    Represents an Http connection to a remote endpoint. Everything in this class is non-blocking.
    """
    __slots__ = ('_bootstrap', '_tls_connection_options', '_on_connection_shutdown', '_native_handle')

    # don't call me, I'm private
    def __init__(self, bootstrap, on_connection_shutdown, tls_connection_options):
        assert isinstance(bootstrap, ClientBootstrap)
        assert tls_connection_options is None or isinstance(tls_connection_options, TlsConnectionOptions)

        for slot in self.__slots__:
            setattr(self, slot, None)

        self._bootstrap = bootstrap
        self._tls_connection_options = tls_connection_options
        self._on_connection_shutdown = on_connection_shutdown
        self._native_handle = None

    @staticmethod
    def new_connection(bootstrap, host_name, port, socket_options,
                       on_connection_shutdown=None, tls_connection_options=None):
        """
        Initiates a new connection to host_name and port using socket_options and tls_connection_options if supplied.
        if tls_connection_options is None, then the connection will be attempted over plain-text.
        on_connection_shutdown will be invoked if the connection shuts-down while you still hold a reference to it.
        on_connection_shutdown takes a single argument of int type, to specify the shutdown reason.

        returns a future where the result is a new instance to HttpClientConnection, once the connection has completed
        and is ready for use.
        """
        assert tls_connection_options is None or isinstance(tls_connection_options, TlsConnectionOptions)
        assert host_name is not None
        assert port is not None
        assert socket_options is not None and isinstance(socket_options, SocketOptions)

        future = Future()
        connection = HttpClientConnection(bootstrap, on_connection_shutdown, tls_connection_options)

        def on_connection_setup_native_cb(native_handle, error_code):
            if error_code == 0:
                connection._native_handle = native_handle
                future.set_result(connection)
            else:
                future.set_exception(Exception("Error during connect: err={}".format(error_code)))

        try:
            if tls_connection_options is not None:
                internal_conn_options_handle = tls_connection_options._internal_tls_conn_options
            else:
                internal_conn_options_handle = None

            _aws_crt_python.aws_py_http_client_connection_create(bootstrap._internal_bootstrap,
                                                                 on_connection_setup_native_cb,
                                                                 connection._on_connection_shutdown,
                                                                 host_name,
                                                                 port,
                                                                 socket_options,
                                                                 internal_conn_options_handle)

        except Exception as e:
            future.set_exception(e)

        return future

    def close(self):
        """
        Closes the connection, if you hold a reference to this instance of HttpClientConnection, on_connection_shutdown
        will be invoked upon completion of the connection close.
        """
        if self._native_handle is not None:
            _aws_crt_python.aws_py_http_client_connection_close(self._native_handle)

    def is_open(self):
        """
        Returns True if the connection is open and usable, False otherwise.
        """
        if self._native_handle is not None:
            return _aws_crt_python.aws_py_http_client_connection_is_open(self._native_handle)

        return False

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
            request._stream = _aws_crt_python.aws_py_http_client_connection_make_request(self._native_handle,
                                                                                         request,
                                                                                         on_stream_completed,
                                                                                         on_incoming_headers_received)

        except Exception as e:
            request.response_headers_received.set_exception(e)

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
