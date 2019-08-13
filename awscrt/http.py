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

#import ptvsd;
#ptvsd.break_into_debugger()
"""
Base class for http connection
"""
class HttpConnection(object):
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
        assert tls_connection_options is None or isinstance(
            tls_connection_options, TlsConnectionOptions)
        assert host_name is not None
        assert port is not None
        assert socket_options is not None and isinstance(
            socket_options, SocketOptions)

        future = Future()
        connection = HttpClientConnection(
            bootstrap, on_connection_shutdown, tls_connection_options)

        def on_connection_setup_native_cb(native_handle, error_code):
            if error_code == 0:
                connection._native_handle = native_handle
                future.set_result(connection)
            else:
                future.set_exception(
                    Exception("Error during connect: err={}".format(error_code)))

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

    def make_request(self, method, uri_str, outgoing_headers, outgoing_body, on_incoming_body):
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
        request = HttpRequest(self, method, uri_str,
                              outgoing_headers, outgoing_body, on_incoming_body)

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


class ServerConnection(HttpConnection):
    """
    Represents an Http server connection. Everything in this class is non-blocking.
    """

    def __init__(self, on_incoming_request, on_shutdown):
        assert on_incoming_request is not None
        self._on_incoming_request = on_incoming_request
        HttpConnection.__init__(self, on_shutdown)
    
    @staticmethod
    def new_server_connection(connection, on_incoming_request, on_shutdown = None):
        """
        create a new server connection, usually it will be called from the on_incoming connection callback, whenever a new connection is accepted.
        """
        server_connection = ServerConnection(on_incoming_request, on_shutdown)
        server_connection._native_handle = connection
        _aws_crt_python.aws_py_http_connection_configure_server(server_connection._native_handle, on_incoming_request, on_shutdown)
        return server_connection

class HttpServer(object):
    """
    Represents an Http server. Everything in this class is non-blocking.
    """
    __slots__ = ('_bootstrap', '_tls_connection_options', '_on_incoming_connection',
                 '_on_destroy_complete', '_native_handle')

    # don't call me, I'm private
    def __init__(self, bootstrap, on_incoming_connection, on_destroy_complete, tls_connection_options):
        assert isinstance(bootstrap, ServerBootstrap)
        assert tls_connection_options is None or isinstance(
            tls_connection_options, TlsConnectionOptions)

        for slot in self.__slots__:
            setattr(self, slot, None)

        self._bootstrap = bootstrap
        self._tls_connection_options = tls_connection_options
        self._on_incoming_connection = on_incoming_connection
        self._on_destroy_complete = on_destroy_complete
        self._native_handle = None

    @staticmethod
    def new_server(bootstrap, host_name, port, socket_options, on_incoming_connection,
                   on_destroy_complete=None, tls_connection_options=None):
        """
        Create a new server listener, binding to the host_name and port. 
        When a new connection is received, the on_incoming_connection cb will be fired, a new ServerConnection obj will be created.
        The new_server_connection() need to be called from the callback to configure the ServerConnection 
        """
        assert tls_connection_options is None or isinstance(
            tls_connection_options, TlsConnectionOptions)
        assert host_name is not None
        assert port is not None
        assert socket_options is not None and isinstance(
            socket_options, SocketOptions)
        assert on_incoming_connection is not None
        if tls_connection_options is not None:
            internal_conn_options_handle = tls_connection_options._internal_tls_conn_options
        else:
            internal_conn_options_handle = None
        server = HttpServer(bootstrap, on_incoming_connection,
                            on_destroy_complete, tls_connection_options)
        server._native_handle = _aws_crt_python.aws_py_http_server_create(
            bootstrap._internal_bootstrap, on_incoming_connection, on_destroy_complete, host_name, port, socket_options, internal_conn_options_handle)
        return server

    def release(self):
        """
        release the server, no more connections will be accepted, when the server finishes destroy process, the on_destroy_complete will be invoked
        """
        future = Future()
        try:
            if self._native_handle is not None:
                _aws_crt_python.aws_py_http_server_realease(
                    self._native_handle)
        except Exception as e:
            future.set_exception(e)

        return future

class HttpRequestHandler(object):
    """
    Request handler object. Create a new one when the on_incoming_request() callback is invoked to handler the request.
    User can know the detail of the request, when the provided callbacks are fired. 
    User can send response back to the request
    """
    __slots__ = ('_connection', 'path_and_query', 'method', '_on_incoming_body', '_stream',
                    'has_request_body', 'request_headers_received', 'stream_completed', '_on_request_completed')

    def __init__(self, connection, on_incoming_body, on_request_completed):
        assert connection is not None and isinstance(connection, ServerConnection)

        self._connection = connection
        self._on_incoming_body = on_incoming_body
        self._on_request_completed = on_request_completed

        self._stream = None
        self.path_and_query = None
        self.method = None
        self.has_request_body = None
    

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
    __slots__ = ('_connection', 'path_and_query', 'method', 'outgoing_headers', '_outgoing_body', '_on_incoming_body', '_stream',
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
