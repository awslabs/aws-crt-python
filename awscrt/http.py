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
from awscrt.io import ClientBootstrap, TlsConnectionOptions, SocketOptions, ServerBootstrap


class HttpClientConnection(object):
    """
    Represents an Http connection to a remote endpoint. Everything in this class is non-blocking.
    """
    __slots__ = ('_bootstrap', '_tls_connection_options', '_on_connection_shutdown', '_native_handle')

    # don't call me, I'm private
    def __init__(self, bootstrap, on_connection_shutdown, tls_connection_options):
        assert isinstance(bootstrap, ClientBootstrap)
        assert tls_connection_options is None or isinstance(
            tls_connection_options, TlsConnectionOptions)

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

    def make_request(self, method, uri_str, outgoing_headers, outgoing_body, on_incoming_body):
        """
        path_and_query is the path and query portion
        of a URL. method is the http method (GET, PUT, etc...). outgoing_headers are the headers to send as part
        of the request.

        outgoing_body is an io.IOBase object that is used to stream the request body. Data will be read out of the stream
    until EOS is reached. The most common usages will be io.StringIO, file objects (via the global open/close functions),
    and io.BinaryIO.

        on_incoming_body is invoked as the response body is received. It takes a single argument of type bytes.

        Makes an Http request. When the headers from the response are received, the returned
        HttpRequest.response_headers_received future will have a result.
        and request.response_headers will be filled in, and request.response_code will be available.
        After this future completes, you can get the result of request.response_completed,
        for the remainder of the response.
        """
        request = HttpRequest(self, method, uri_str, outgoing_headers, outgoing_body, on_incoming_body)

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


'''
TODO: Server Connection class,and configure the server connection.
'''


class HttpServer(object):
    """
    Represents an Http server. Everything in this class is non-blocking.
    """
    __slots__ = ('_bootstrap', '_tls_connection_options', '_on_incoming_connection',
                 '_on_destroy_complete', '_native_handle', '_destroy_complete')

    def __init__(self, bootstrap, host_name, port, socket_options, on_incoming_connection, tls_connection_options=None):
        """
        Create a new server listener, binding to the host_name and port. 
        When a new connection is received, the on_incoming_connection cb will be fired, a new ServerConnection obj will be created.
        The aws_py_http_connection_configure_server need to be called from the callback to configure the ServerConnection 
        @param socket_options: awscrt.io.SocketOptions for the server's listening socket. Required
        @param on_incoming_connection: Callback with signature (connection: HttpConnection.native_handle, error_code: int) Required
        @param bootstrap: awscrt.io.ServerBootstrap. Required
        @param tls_connection_options: awscrt.io.TlsConnectionOptions, for TLS connection
        """
        assert isinstance(bootstrap, ServerBootstrap)
        assert tls_connection_options is None or isinstance(tls_connection_options, TlsConnectionOptions)
        assert host_name is not None
        assert port is not None
        assert isinstance(socket_options, SocketOptions)
        assert on_incoming_connection is not None
        for slot in self.__slots__:
            setattr(self, slot, None)

        def on_destroy_complete(server_native_handle):
            self._destroy_complete.set_result(True)

        self._bootstrap = bootstrap
        self._tls_connection_options = tls_connection_options
        self._on_incoming_connection = on_incoming_connection
        self._on_destroy_complete = on_destroy_complete
        self._native_handle = None
        self._destroy_complete = Future()

        if tls_connection_options is not None:
            internal_conn_options_handle = tls_connection_options._internal_tls_conn_options
        else:
            internal_conn_options_handle = None

        self._native_handle = _aws_crt_python.aws_py_http_server_create(
            bootstrap._internal_bootstrap, on_incoming_connection, on_destroy_complete, host_name, port, socket_options,
            internal_conn_options_handle)

    def close(self):
        """
        close the server, no more connections will be accepted, a future object will be returned, and when the close process finishes
        the future result or exception will be set.
        """
        _aws_crt_python.aws_py_http_server_release(self._native_handle)
        return self._destroy_complete


class HttpRequest(object):
    """
    Represents an HttpRequest to pass to HttpClientConnection.make_request(). path_and_query is the path and query portion
    of a URL. method is the http method (GET, PUT, etc...). outgoing_headers are the headers to send as part
    of the request.

    outgoing_body is an io.IOBase object that is used to stream the request body. Data will be read out of the stream
    until EOS is reached. The most common usages will be io.StringIO, file objects (via the global open/close functions),
    and io.BinaryIO.

    on_incoming_body is invoked as the response body is received. It takes a single argument of type bytes.
    """
    __slots__ = (
        '_connection', 'path_and_query', 'method', 'outgoing_headers', '_outgoing_body', '_on_incoming_body', '_stream',
        'response_headers', 'response_code', 'has_response_body', 'response_headers_received',
        'response_completed')

    def __init__(self, connection, method, path_and_query, outgoing_headers, outgoing_body, on_incoming_body):
        from io import IOBase

        assert method is not None
        assert outgoing_headers is not None
        assert connection is not None and isinstance(connection, HttpClientConnection)
        assert not outgoing_body or isinstance(outgoing_body, IOBase)

        self.path_and_query = path_and_query

        if path_and_query is None:
            self.path_and_query = '/'

        self._connection = connection
        self.method = method
        self.outgoing_headers = outgoing_headers
        self._outgoing_body = outgoing_body
        self._on_incoming_body = on_incoming_body
        self.response_completed = Future()
        self.response_headers_received = Future()
        self._stream = None
        self.response_headers = None
        self.response_code = None
        self.has_response_body = False
