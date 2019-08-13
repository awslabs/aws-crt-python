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


log_level = io.LogLevel.NoLogs
log_level = io.LogLevel.Error
log_output = 'stderr'
io.init_logging(log_level, log_output)

class TestStringMethods(unittest.TestCase):

    def test_server_bootstrap(self):
        # an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
        # you only want one of these.
        event_loop_group = io.EventLoopGroup(1)
        server_bootstrap = io.ServerBootstrap(event_loop_group)
        self.assertIsNotNone(server_bootstrap)

    def test_server_create_destroy(self):

        #Settings for tests
        host_name = str(random.random())
        port = 0
        tls = False
        connect_timeout = 3000

        def on_incoming_connection(server, connection, error_code):
            print("fake on incoming connection!")
        
        def on_destroy_complete(server):
            future.set_result("destroy completed!")
        # an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
        # you only want one of these.
        event_loop_group = io.EventLoopGroup(1)
        server_bootstrap = io.ServerBootstrap(event_loop_group)
        if sys.platform == 'win32':
            #win32
            host_name = "\\\\.\\pipe\\testsock-" + host_name
        else:
            host_name = "testsock-{}.sock".format(host_name)
        tls_connection_options = None
        socket_options = io.SocketOptions()
        socket_options.connect_timeout_ms = connect_timeout
        socket_options.domain = io.SocketDomain.Local
        server = http.HttpServer.new_server(server_bootstrap, host_name, port, socket_options, on_incoming_connection, on_destroy_complete)
        print("Server create success")
        future = http.HttpServer.release(server)
        print(future.result())

        print("SUCCESS!")
        #delete the socket, cleanup
        os.system("rm {}".format(host_name))

        
if __name__ == '__main__':
    unittest.main()

# server bootstrap init

