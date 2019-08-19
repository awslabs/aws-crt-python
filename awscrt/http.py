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

# import ptvsd;
# ptvsd.break_into_debugger()
"""
Base class for http connection
"""


class HttpConnection(object):
    """
    Father Class of HttpClientConnection and HttpServerConnection. Meaningless if called individually.
    """
    __slots__ = ('_on_connection_shutdown', '_native_handle')

    def __init__(self, on_connection_shutdown):
        for slot in self.__slots__:
            setattr(self, slot, None)

        self._on_connection_shutdown = on_connection_shutdown
        self._native_handle = None

    def close(self):
        """
        Closes the connection, if you hold a reference to this instance of HttpClientConnection, on_connection_shutdown
        will be invoked upon completion of the connection close.
        """
        if self._native_handle is not None:
            _aws_crt_python.aws_py_http_connection_close(
                self._native_handle)

    def is_open(self):
        """
        Returns True if the connection is open and usable, False otherwise.
        """
        if self._native_handle is not None:
            return _aws_crt_python.aws_py_http_connection_is_open(self._native_handle)

        return False


class HttpClientConnection(HttpConnection):
    """
    Represents an Http connection to a remote endpoint. Everything in this class is non-blocking.
    """

    # don't call me, I'm private
    def __init__(self, bootstrap, on_connection_shutdown, tls_connection_options):

        assert isinstance(bootstrap, ClientBootstrap)
        assert tls_connection_options is None or isinstance(
            tls_connection_options, TlsConnectionOptions)

        self._tls_connection_options = tls_connection_options
        self._bootstrap = bootstrap
        HttpConnection.__init__(self, on_connection_shutdown)

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

    def make_request(self, method, uri_str, outgoing_headers, outgoing_body, on_incoming_body = None):
        """
        path_and_query is the path and query portion
        of a URL. method is the http method (GET, PUT, etc...). outgoing_headers are the headers to send as part
        of the request.

        #TODO
        outgoing_body is invoked to read the body of the request. It takes a single parameter of type MemoryView
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

        request = HttpRequest(self, method, uri_str, outgoing_headers, outgoing_body, on_incoming_body)

        def on_stream_completed(error_code):
            request.response_completed.set_result(error_code)

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


class ServerConnection(HttpConnection):
    """
    Represents an Http server connection. Everything in this class is non-blocking.
    """

    def __init__(self, on_incoming_request, on_shutdown):
        """
        private
        """
        assert on_incoming_request is not None
        self._on_incoming_request = on_incoming_request
        HttpConnection.__init__(self, on_shutdown)

    @staticmethod
    def new_server_connection(connection, on_incoming_request, on_shutdown=None):
        """
        create a new server connection, usually it will be called from the on_incoming connection callback, whenever a new connection is accepted.

        on_incoming_request is invoked whenever a new request is received from the connection. It takes http.HttpConnection._native_handle as argument
        and it has to call http.HttpRequestHandler() to create a new request handler to handle the request
        on_shutdown is invoked as the connection is shutted down. It takes http.HttpConnection._native_handle and error_code as argument
        """
        server_connection = ServerConnection(on_incoming_request, on_shutdown)
        server_connection._native_handle = connection
        _aws_crt_python.aws_py_http_connection_configure_server(server_connection._native_handle, on_incoming_request,
                                                                on_shutdown)
        return server_connection


class HttpServer(object):
    """
    Represents an Http server. Everything in this class is non-blocking.
    """
    __slots__ = ('_bootstrap', '_tls_connection_options', '_on_incoming_connection',
                 '_on_destroy_complete', '_native_handle', '_destroy_complete', '_initial_window_size')

    def __init__(self, bootstrap, host_name, port, socket_options, on_incoming_connection, initial_window_size=-1,
                 tls_connection_options=None):
        """
        Create a new server listener, binding to the host_name and port. 
        When a new connection is received, the on_incoming_connection cb will be fired, a new ServerConnection obj will be created.
        The aws_py_http_connection_configure_server need to be called from the callback to configure the ServerConnection 
        
        socket_options: awscrt.io.SocketOptions for the server's listening socket. Required
        on_incoming_connection: Callback with signature (connection: HttpConnection.native_handle, error_code: int) Required
        user must call http.ServerConnection.new_server_connection() to configure the connection in this callback or the connection will fail
        bootstrap: awscrt.io.ServerBootstrap. Required
        tls_connection_options: awscrt.io.TlsConnectionOptions, for TLS connection
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
        self._initial_window_size = initial_window_size

        if tls_connection_options is not None:
            internal_conn_options_handle = tls_connection_options._internal_tls_conn_options
        else:
            internal_conn_options_handle = None

        self._native_handle = _aws_crt_python.aws_py_http_server_create(
            bootstrap._internal_bootstrap, on_incoming_connection, on_destroy_complete, host_name, port,
            initial_window_size, socket_options,
            internal_conn_options_handle)

    def close(self):
        """
        close the server, no more connections will be accepted, a future object will be returned, and when the close process finishes
        the future result or exception will be set.
        """
        try:
            _aws_crt_python.aws_py_http_server_release(self._native_handle)
        except Exception as e:
            self._destroy_complete.set_exception(e)

        return self._destroy_complete


class HttpRequestHandler(object):
    """
    Request handler object. Create a new one when the on_incoming_request() callback is invoked to handler the request.
    User can know the detail of the request, when the provided callbacks are fired. 
    User can send response back to the request
    """
    __slots__ = ('_connection', 'path_and_query', 'method', '_on_incoming_body', '_stream', 'request_headers',
                 'has_request_body', '_native_handle', '_on_request_done', '_stream_completed', 'has_incoming_body'
                 , 'request_header_received')

    def __init__(self, connection, on_incoming_body=None, on_request_done=None):
        """
        ONLY CALLED FROM on_incoming_request CALLBACK
        
        connection is http.HttpConnection._native_handle object
        on_incoming_body is invoked as the request body is received. It takes a single argument of type bytes.
        on_request_done is invoked as the request finished receiving. It takes no argument but have to 
        return an bool as Error or not (False to continue processing the stream, True to indicate failure and cancel the stream) 
        """
        assert connection is not None

        def on_stream_completed(error_code):
            self._stream_completed.set_result(error_code)

        def on_request_headers_received(headers, method, uri, has_body):
            self.request_headers = headers
            self.method = method
            self.path_and_query = uri
            self.has_incoming_body = has_body
            self.request_header_received.set_result(True)

        for slot in self.__slots__:
            setattr(self, slot, None)

        self._connection = connection
        self._on_incoming_body = on_incoming_body
        self._on_request_done = on_request_done

        self._stream = None
        self.path_and_query = None
        self.method = None
        self.has_request_body = None
        self.request_headers = None
        self._native_handle = None
        self.has_incoming_body = None

        self._stream_completed = Future()
        self.request_header_received = Future()

        self._native_handle = _aws_crt_python.aws_py_http_stream_new_server_request_handler(self._connection,
                                                                                            on_stream_completed,
                                                                                            on_request_headers_received,
                                                                                            self._on_incoming_body,
                                                                                            self._on_request_done)

    def send_response(self, response):
        try:
            _aws_crt_python.aws_py_http_stream_server_send_response(self._native_handle, response)

        except Exception as e:
            print(e)
        return self._stream_completed

class HttpResponse(object):
    """
    Represents an HttpResponse to pass to HttpRequestHandler.send_response(). status is response status code (3 digital int)
    outgoing_headers are the headers to send as part of the response.
    
    #TODO WAT
    outgoing_body is invoked to read the body of the response. It takes a single parameter of type MemoryView
    (it's writable), and you signal the end of the stream by returning OutgoingHttpBodyState.Done for the first tuple
    argument. If you aren't done sending the body, the first tuple argument should be OutgoingHttpBodyState.InProgress
    The second tuple argument is the size of the data written to the memoryview.
    """
    __slots__ = ('status', 'outgoing_headers', '_outgoing_body')

    def __init__(self, status, outgoing_headers, outgoing_body=None):
        import io

        assert status is not None
        assert outgoing_headers is not None
        assert not outgoing_body or isinstance(outgoing_body, io.IOBase)

        for slot in self.__slots__:
            setattr(self, slot, None)
        self.status = status
        self.outgoing_headers = outgoing_headers
        self._outgoing_body = outgoing_body


class HttpRequest(object):
    """
    Represents an HttpRequest to pass to HttpClientConnection.make_request(). path_and_query is the path and query portion
    of a URL. method is the http method (GET, PUT, etc...). outgoing_headers are the headers to send as part
    of the request.

    #TODO WAT
    outgoing_body is invoked to read the body of the request. It takes a single parameter of type MemoryView
    (it's writable), and you signal the end of the stream by returning OutgoingHttpBodyState.Done for the first tuple
    argument. If you aren't done sending the body, the first tuple argument should be OutgoingHttpBodyState.InProgress
    The second tuple argument is the size of the data written to the memoryview.

    on_incoming_body is invoked as the response body is received. It takes a single argument of type bytes.
    """
    __slots__ = (
        '_connection', 'path_and_query', 'method', 'outgoing_headers', '_outgoing_body', '_on_incoming_body', '_stream',
        'response_headers', 'response_code', 'has_response_body', 'response_headers_received',
        'response_completed')

    def __init__(self, connection, method, path_and_query, outgoing_headers, outgoing_body, on_incoming_body):
        import io

        assert method is not None
        assert outgoing_headers is not None
        assert connection is not None and isinstance(
            connection, HttpClientConnection)
        assert not outgoing_body or isinstance(outgoing_body, io.IOBase)

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
