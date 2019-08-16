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
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
# log settings
log_level = io.LogLevel.NoLogs
log_level = io.LogLevel.Error
log_output = 'stderr'
io.init_logging(log_level, log_output)


def print_header_list(headers):
    for key, value in headers.items():
        print('{}: {}'.format(key, value))



class TestClient(unittest.TestCase):

    def test_server_create_destroy(self):

        # an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
        # you only want one of these.
        event_loop_group = io.EventLoopGroup(1)

        # client bootstrap knows how to connect all the pieces. In this case it also has the default dns resolver
        # baked in.
        client_bootstrap = io.ClientBootstrap(event_loop_group)
        url = urlparse("http://httpbin.org/post")
        port = 443
        scheme = 'https'
        if url.scheme is not None and url.scheme == 'http':
            scheme = 'http'
        
        if url.port is not None:
            port = url.port
        else:
            if scheme == 'http':
                port = 80

        tls_connection_options = None

        output = getattr(sys.stdout, 'buffer', sys.stdout)
        method = 'POST'
        # invoked up on the connection closing
        def on_connection_shutdown(err_code):
            print('connection close with error code {}'.format(err_code))


        # invoked by the http request call as the response body is received in chunks
        def on_incoming_body(body_data):
            print(body_data)                

        data_bytes = "\"{'test':'testval'}\"".encode(encoding='utf-8')
        data_len = len(data_bytes)
        data_stream = BytesIO(data_bytes)

        print("Sending {} bytes as body".format(data_len))

        socket_options = io.SocketOptions()
        socket_options.connect_timeout_ms = 3000
        hostname = url.hostname
        connect_future = http.HttpClientConnection.new_connection(client_bootstrap, hostname, port, socket_options,
                                                                on_connection_shutdown, tls_connection_options)
        connection = connect_future.result()
        outgoing_headers = {'host': hostname, 'user-agent': 'elasticurl.py 1.0, Powered by the AWS Common Runtime.', 'content-type': 'application/json'}
        
        uri_str = url.path

        if uri_str is None or uri_str == '':
            uri_str = '/'

        if url.query is not None:
            uri_str += url.query
        # invoked as soon as the response headers are received
        def response_received_cb(ftr):
            print('Response Code: {}'.format(request.response_code))
            print_header_list(request.response_headers)
        
        if data_len != 0:
            outgoing_headers['content-length'] = str(data_len)
        # make the request
        request = connection.make_request(method, uri_str, outgoing_headers, data_stream, on_incoming_body)
        request.response_headers_received.add_done_callback(response_received_cb)

        # wait for response headers
        response_start = request.response_headers_received.result(timeout=10)

        # wait until the full response is finished
        response_finished = request.response_completed.result(timeout=10)
        request = None
        connection = None

        if data_stream is not None:
            data_stream.close()

if __name__ == '__main__':
    unittest.main()
