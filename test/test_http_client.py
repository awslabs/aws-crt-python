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

import awscrt.http
from collections import namedtuple
import http.server
import unittest

class Response(object):
    def __init__(self):
        self.status_code = None
        self.headers = None
        self.body = bytearray()

    def on_response(self, stream, status_code, headers):
        self.status_code = status_code
        self.headers = headers

    def on_body(self, stream, chunk):
        self.body.extend(chunk)

class TestHttpClientConnection(unittest.TestCase):
    hostname = 'localhost'
    port = 8000
    timeout = 10 # seconds

    def test_connect(self):
        server = http.server.HTTPServer((self.hostname, self.port), http.server.SimpleHTTPRequestHandler)

        # connect
        connection_future = awscrt.http.HttpClientConnection.new(self.hostname, self.port)
        connection = connection_future.result(self.timeout)
        self.assertTrue(connection.is_open())

        # register shutdown callback
        shutdown_callback_results = []
        def shutdown_callback(error_code):
            shutdown_callback_results.append(error_code)

        connection.add_shutdown_callback(shutdown_callback)

        # close connection
        close_future = connection.close()
        shutdown_error_code_from_close_future = close_future.result(self.timeout)

        # assert that error code was reported via close_future and shutdown callback
        # error_code should be 0 (normal shutdown)
        self.assertEqual(0, shutdown_error_code_from_close_future)
        self.assertEqual(1, len(shutdown_callback_results))
        self.assertEqual(0, shutdown_callback_results[0])
        self.assertFalse(connection.is_open())

        server.server_close()


    def test_get_request(self):
        server = http.server.HTTPServer((self.hostname, self.port), http.server.SimpleHTTPRequestHandler)
        connection = awscrt.http.HttpClientConnection.new(self.hostname, self.port).result(self.timeout)

        # client GETs a file that is served from disk.
        target_filename = 'test/files/short.txt'

        request = awscrt.http.HttpRequest("GET", '/' + target_filename)

        response = Response()

        stream = connection.request(request, response.on_response, response.on_body)

        server.handle_request()
        stream.complete_future.result(self.timeout)

        # examine response
        self.assertEqual(200, response.status_code)

        with open(target_filename, 'rb') as target_file:
            target_body = target_file.read()
            self.assertEqual(target_body, response.body)

        # done
        connection.close().result(self.timeout)
        server.server_close()


if __name__ == '__main__':
    unittest.main()
