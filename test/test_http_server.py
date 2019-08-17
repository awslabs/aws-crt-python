# Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import argparse
import sys
import os
from io import BytesIO
from awscrt import io, http
import unittest
import random
from concurrent.futures import Future

log_level = io.LogLevel.NoLogs
log_level = io.LogLevel.Error
log_output = 'stderr'
io.init_logging(log_level, log_output)


def print_header_list(headers):
    for key, value in headers.items():
        print('{}: {}'.format(key, value))


class TestServerConnection(unittest.TestCase):
    def setUp(self):

        # an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of
        # connections you only want one of these.
        random.seed()
        host_name = str(random.random())
        self.port = 0
        tls = False
        connect_timeout = 3000
        self.event_loop_group = io.EventLoopGroup(1)
        self.server_bootstrap = io.ServerBootstrap(self.event_loop_group)
        if sys.platform == 'win32':
            # win32
            self.host_name = "\\\\.\\pipe\\testsock-" + host_name
        else:
            self.host_name = "testsock-{}.sock".format(host_name)
        self.socket_options = io.SocketOptions()
        self.socket_options.connect_timeout_ms = connect_timeout
        self.socket_options.domain = io.SocketDomain.Local
        self.tls_connection_options = None

    def test_server_bootstrap(self):
        # an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of
        # connections you only want one of these.
        self.assertIsNotNone(self.server_bootstrap)

    def test_server_create_destroy(self):
        print("----TEST SERVER_CREATE_DESTROY BEGIN!----")

        def on_incoming_connection(server, connection, error_code):
            print("----fake on incoming connection!----")

        server = http.HttpServer(self.server_bootstrap, self.host_name, self.port, self.socket_options,
                                 on_incoming_connection)
        print("----Server create success----")
        future = http.HttpServer.close(server)
        if future.result():
            print("----TEST SERVER_CREATE_DESTROY SUCCESS!----")
            print("\n")

    def test_server_create_no_close_called(self):
        print("----TEST SERVER_CREATE_DESTROY_NO_CLOSE_CALLED BEGIN!----")

        def on_incoming_connection(server, connection, error_code):
            print("----fake on incoming connection!----")

        server = http.HttpServer(self.server_bootstrap, self.host_name, self.port, self.socket_options,
                                 on_incoming_connection)
        print("----Server create success----")
        print("----Let destructor to clean it up----")
        print("\n")

    def test_server_connection(self):

        print("----TEST SERVER_CONNECTION BEGIN!----")

        def on_incoming_request(connection):
            print("----fake on incoming request----")

        def on_server_conn_shutdown(connection, error_code):
            print(
                "----shutdown server connection with error_code: {}----".format(error_code))

        def on_incoming_connection(connection, error_code):
            # configure the connection here!
            if error_code:
                print("----server connection fail with error_code: {}----".format(error_code))
                server_conn_future.set_exception(Exception("Error during connect: err={}".format(error_code)))
            server_connection = http.ServerConnection.new_server_connection(connection, on_incoming_request,
                                                                            on_server_conn_shutdown)
            server_conn_future.set_result(server_connection)

        # server setup
        server_conn_future = Future()
        server = http.HttpServer(self.server_bootstrap, self.host_name, self.port, self.socket_options,
                                 on_incoming_connection)
        print("----server setup completed!----")
        # client setup
        # invoked up on the connection closing
        client_conn_shutdown_future = Future()

        def on_connection_shutdown(err_code):
            client_conn_shutdown_future.set_result(
                '----client connection close with error code {}----'.format(err_code))

        # client bootstrap knows how to connect all the pieces. In this case it also has the default dns resolver
        # baked in.
        client_bootstrap = io.ClientBootstrap(self.event_loop_group)
        print("----MAKE NEW CONNECTION NOW-----")
        connect_future = http.HttpClientConnection.new_connection(client_bootstrap, self.host_name, self.port,
                                                                  self.socket_options,
                                                                  on_connection_shutdown, self.tls_connection_options)
        connection = connect_future.result()
        self.assertIsNotNone(connection)
        # wait for server connection setup
        server_connection = server_conn_future.result()
        # release the server
        destroy_future = http.HttpServer.close(server)
        if destroy_future.result():
            print("----SERVER DESTROY FINISHED----")

        # wait client side connection to shutdown
        print(client_conn_shutdown_future.result())

        # done
        print("----TEST SERVER_CONNECTION SUCCESS!----")
        print("\n")


class TestServerRequestResponse(unittest.TestCase):

    def on_incoming_body(self, body_data):
        print(str(body_data, encoding='utf-8'))

    def setUp(self):

        # an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of
        # connections you only want one of these.
        random.seed()
        host_name = str(random.random())
        self.port = 0
        tls = False
        connect_timeout = 3000
        self.event_loop_group = io.EventLoopGroup(1)
        self.server_bootstrap = io.ServerBootstrap(self.event_loop_group)
        if sys.platform == 'win32':
            # win32
            self.host_name = "\\\\.\\pipe\\testsock-" + host_name
        else:
            self.host_name = "testsock-{}.sock".format(host_name)
        self.socket_options = io.SocketOptions()
        self.socket_options.connect_timeout_ms = connect_timeout
        self.socket_options.domain = io.SocketDomain.Local
        self.tls_connection_options = None

        self.output = getattr(sys.stdout, 'buffer', sys.stdout)

        self.server_request_done_futrue = Future()

        def server_request_done():
            self.server_request_done_futrue.set_result(True)
            Error = False
            return Error

        def on_incoming_request(connection):
            request_handler = http.HttpRequestHandler(connection, self.on_incoming_body, server_request_done)
            self.request_handler_future.set_result(request_handler)
            return request_handler._native_handle

        def on_server_conn_shutdown(connection, error_code):
            print("----shutdown server connection with error_code: {}----".format(error_code))

        def on_incoming_connection(connection, error_code):
            # configure the connection here!
            if error_code:
                print("----server connection fail with error_code: {}----".format(error_code))
                self.server_conn_future.set_exception(Exception("Error during connect: err={}".format(error_code)))
            server_connection = http.ServerConnection.new_server_connection(connection, on_incoming_request,
                                                                            on_server_conn_shutdown)
            self.server_conn_future.set_result(server_connection)

        # server setup
        self.server_conn_future = Future()
        self.request_handler_future = Future()
        server = http.HttpServer(self.server_bootstrap, self.host_name, self.port, self.socket_options,
                                 on_incoming_connection)
        # client setup
        self.client_conn_shutdown_future = Future()

        def on_connection_shutdown(err_code):
            self.client_conn_shutdown_future.set_result(
                '----client connection close with error code {}----'.format(err_code))

        client_bootstrap = io.ClientBootstrap(self.event_loop_group)
        connect_future = http.HttpClientConnection.new_connection(client_bootstrap, self.host_name, self.port,
                                                                  self.socket_options,
                                                                  on_connection_shutdown, self.tls_connection_options)
        self.client_connection = connect_future.result()
        # wait for server connection setup
        self.server_connection = self.server_conn_future.result()
        # connections success

    def test_server_request_response_1line(self):
        print("----test_server_request_response_1line BEGIN!----")

        def response_received_cb(ftr):
            self.assertEqual(request.response_code, response_status)

        method = 'GET'
        uri_str = '/'
        outgoing_headers = {}
        data_stream = None

        # make request
        print("----MAKE REQUEST NOW-----")
        request = self.client_connection.make_request(method, uri_str, outgoing_headers, data_stream)
        request.response_headers_received.add_done_callback(response_received_cb)

        # wait for request received
        request_handler = self.request_handler_future.result()
        if request_handler.request_header_received.result():
            self.assertEqual(method, request_handler.method)
            self.assertEqual(uri_str, request_handler.path_and_query)
        if self.server_request_done_futrue.result():
            print("----request receiving done----")

        # make response
        response_headers = {}
        response_status = 200
        response = http.HttpResponse(response_status, response_headers)
        request_handler.send_response(response)

        # wait for response
        response_start = request.response_headers_received.result(timeout=10)

        # wait until the full response is finished
        response_finished = request.response_completed.result(timeout=10)

        # wait for server stream is finished
        self.assertEqual(request_handler.stream_completed.result(), 0)
        # done
        if data_stream is not None:
            data_stream.close()
        print("----test_server_request_response_1line SUCCESS!----")
        print("\n")

    def test_server_request_response_body_from_string(self):
        print("----test_server_request_response_body_from_string BEGIN!----")

        def response_received_cb(ftr):
            self.assertEqual(request.response_code, response_status)
            self.assertEqual(request.response_headers, response_headers)

        method = 'GET'
        uri_str = '/'
        request_headers = {'host': self.host_name,
                           'user-agent': 'elasticurl.py 1.0, Powered by the AWS Common Runtime.'}
        outgoing_data = "----test body from string success----"
        request_data_bytes = outgoing_data.encode(encoding='utf-8')
        request_data_len = len(request_data_bytes)
        request_data_stream = BytesIO(request_data_bytes)
        if request_data_len != 0:
            request_headers['content-length'] = str(request_data_len)

        # make request
        print("----MAKE REQUEST NOW-----")
        request = self.client_connection.make_request(method, uri_str, request_headers, request_data_stream,
                                                      self.on_incoming_body)
        request.response_headers_received.add_done_callback(response_received_cb)

        # wait for request received
        request_handler = self.request_handler_future.result()
        if request_handler.request_header_received.result():
            self.assertEqual(method, request_handler.method)
            self.assertEqual(uri_str, request_handler.path_and_query)
            self.assertEqual(request_handler.request_headers, request_headers)

        if self.server_request_done_futrue.result():
            print("----request decode done----")

        # make response
        response_headers = {'Date': "Fri, 01 Mar 2019 17:18:55 GMT",
                            'user-agent': 'elasticurl.py 1.0, Powered by the AWS Common Runtime.'}
        response_body = outgoing_data.encode(encoding='utf-8')
        response_body_stream = BytesIO(response_body)
        if len(response_body) != 0:
            response_headers['content-length'] = str(len(response_body))

        response_status = 308
        response = http.HttpResponse(response_status, response_headers, response_body_stream)
        request_handler.send_response(response)

        # wait for response
        response_start = request.response_headers_received.result(timeout=10)
        # wait until the full response is finished
        response_finished = request.response_completed.result(timeout=10)

        # wait for server stream close
        self.assertEqual(request_handler.stream_completed.result(), 0)
        # done
        if request_data_stream is not None:
            request_data_stream.close()
        if response_body_stream is not None:
            response_body_stream.close()
        print("----test_server_request_response_body_from_string SUCCESS!----")
        print("\n")

    def test_server_request_response_body_from_file(self):
        print("----test_server_request_response_body_from_file BEGIN!----")

        # make request
        def response_received_cb(ftr):
            self.assertEqual(request.response_code, response_status)
            self.assertEqual(request.response_headers, response_headers)

        method = 'GET'
        uri_str = '/'
        request_headers = {'host': self.host_name,
                           'user-agent': 'elasticurl.py 1.0, Powered by the AWS Common Runtime.'}
        data_file = "http_test_body.txt"
        request_data_len = os.stat(data_file).st_size
        request_data_stream = open(data_file, 'rb')
        if request_data_len != 0:
            request_headers['content-length'] = str(request_data_len)
        # wait for server connection setup
        server_connection = self.server_conn_future.result()
        # make request
        print("----MAKE REQUEST NOW-----")
        request = self.client_connection.make_request(method, uri_str, request_headers, request_data_stream,
                                                      self.on_incoming_body)
        request.response_headers_received.add_done_callback(response_received_cb)

        # wait for request received
        request_handler = self.request_handler_future.result()
        if request_handler.request_header_received.result():
            self.assertEqual(method, request_handler.method)
            self.assertEqual(uri_str, request_handler.path_and_query)
            self.assertEqual(request_handler.request_headers, request_headers)

        if self.server_request_done_futrue.result():
            print("----request decode done----")

        # make response
        response_headers = {'Date': "Fri, 01 Mar 2019 17:18:55 GMT",
                            'user-agent': 'elasticurl.py 1.0, Powered by the AWS Common Runtime.'}

        response_body_len = os.stat(data_file).st_size
        response_body_stream = open(data_file, 'rb')
        if response_body_len != 0:
            response_headers['content-length'] = str(response_body_len)

        response_status = 308
        response = http.HttpResponse(response_status, response_headers, response_body_stream)
        request_handler.send_response(response)

        # wait for response
        response_start = request.response_headers_received.result(timeout=10)
        # wait until the full response is finished
        response_finished = request.response_completed.result(timeout=10)

        # wait for server stream close
        self.assertEqual(request_handler.stream_completed.result(), 0)
        # done
        if request_data_stream is not None:
            request_data_stream.close()
        if response_body_stream is not None:
            response_body_stream.close()
        print("----test_server_request_response_body_from_file SUCCESS!----")
        print("\n")


if __name__ == '__main__':
    unittest.main()
