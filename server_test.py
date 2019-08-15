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

# log settings
log_level = io.LogLevel.NoLogs
log_level = io.LogLevel.Error
log_output = 'stderr'
io.init_logging(log_level, log_output)


def print_header_list(headers):
    for key, value in headers.items():
        print('{}: {}'.format(key, value))


random.seed()
host_name = str(random.random())
port = 0
tls = False
connect_timeout = 3000
server_event_loop_group = io.EventLoopGroup(1)
client_event_loop_group = io.EventLoopGroup(1)
server_bootstrap = io.ServerBootstrap(server_event_loop_group)
if sys.platform == 'win32':
    # win32
    host_name = "\\\\.\\pipe\\testsock-" + host_name
else:
    host_name = "testsock-{}.sock".format(host_name)
socket_options = io.SocketOptions()
socket_options.connect_timeout_ms = connect_timeout
socket_options.domain = io.SocketDomain.Local
tls_connection_options = None

print("----TEST SERVER_REQUEST BEGIN!----")

output = getattr(sys.stdout, 'buffer', sys.stdout)


def server_on_incoming_body(body_data):
    output.write(body_data)
    request_body_future.set_result(True)


def on_incoming_request(connection):
    request_handler = http.HttpRequestHandler(connection, server_on_incoming_body)
    request_handler_future.set_result(request_handler)
    return request_handler._native_handle


def on_server_conn_shutdown(connection, error_code):
    print("----shutdown server connection with error_code: {}----".format(error_code))


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
request_handler_future = Future()
request_body_future = Future()
server = http.HttpServer(server_bootstrap, host_name, port, socket_options, on_incoming_connection)
print("----server setup completed!----")
# client setup
client_conn_shutdown_future = Future()


def on_connection_shutdown(err_code):
    client_conn_shutdown_future.set_result('----client connection close with error code {}----'.format(err_code))


def client_on_incoming_body(body_data):
    output.write(body_data)


def response_received_cb(ftr):
    print('Response Code: {}'.format(request.response_code))
    print_header_list(request.response_headers)


# invoked by the http request call as the response body is received in chunks


# client bootstrap knows how to connect all the pieces. In this case it also has the default dns resolver
# baked in.
client_bootstrap = io.ClientBootstrap(client_event_loop_group)
print("----MAKE NEW CONNECTION NOW-----")
connect_future = http.HttpClientConnection.new_connection(client_bootstrap, host_name, port,
                                                          socket_options,
                                                          on_connection_shutdown, tls_connection_options)
connection = connect_future.result()

method = 'GET'
uri_str = '/'
outgoing_headers = {'host': host_name, 'user-agent': 'elasticurl.py 1.0, Powered by the AWS Common Runtime.'}
outgoing_data = "{'test':'testval'}"
data_bytes = outgoing_data.encode(encoding='utf-8')
data_len = len(data_bytes)
data_stream = BytesIO(data_bytes)
print("Sending {} bytes as body".format(data_len))
if data_len != 0:
    outgoing_headers['content-length'] = str(data_len)
# wait for server connection setup
server_connection = server_conn_future.result()
# make request
print("----MAKE REQUEST NOW-----")
request = connection.make_request(method, uri_str, outgoing_headers, data_stream, client_on_incoming_body)
request.response_headers_received.add_done_callback(response_received_cb)

request_handler = request_handler_future.result()
if request_handler.request_header_received.result():
    print("----REQUEST HEAD RECEIVED-----")
    print("\n")
    print("method:" + request_handler.method)
    print("uri:" + request_handler.path_and_query)
    print_header_list(request_handler.request_headers)
    print("\n")

if request_body_future.result():
    print("body received")

# make response
response_headers = {'Date': "Fri, 01 Mar 2019 17:18:55 GMT",
                    'user-agent': 'elasticurl.py 1.0, Powered by the AWS Common Runtime.'}
response_body = "write more tests"
if len(response_body) != 0:
    response_headers['content-length'] = str(len(response_body))
response = http.HttpResponse(308, response_headers, response_body)
request_handler.send_response(response)

# wait for response
response_start = request.response_headers_received.result(timeout=10)
# wait until the full response is finished
response_finished = request.response_completed.result(timeout=10)

# release the server
destroy_future = http.HttpServer.close(server)
if destroy_future.result():
    print("----SERVER DESTROY FINISHED----")
# wait client side connection to shutdown
print(client_conn_shutdown_future.result())

# wait for server stream close
print(request_handler.stream_completed.result())
# done
if data_stream is not None:
    data_stream.close()
print("----TEST SERVER_REQUEST SUCCESS!----")

# delete the socket, cleanup
os.system("rm {}".format(host_name))

# server bootstrap init
