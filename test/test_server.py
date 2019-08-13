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
random.seed()

class TestStringMethods(unittest.TestCase):

    def init(self, host_name, port, tls, connect_timeout):

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
        return event_loop_group, server_bootstrap, tls_connection_options, socket_options

    def test_server_bootstrap(self):
        # an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
        # you only want one of these.
        event_loop_group = io.EventLoopGroup(1)
        server_bootstrap = io.ServerBootstrap(event_loop_group)
        self.assertIsNotNone(server_bootstrap)

    def test_server_create_destroy(self):
        print("----TEST SERVER_CREATE_DESTROY BEGIN!----")
        def on_incoming_connection(server, connection, error_code):
            print("----fake on incoming connection!----")
        
        def on_destroy_complete(server):
            future.set_result("----destroy completed!----")
        
        #Init for tests
        host_name = str(random.random())
        port = 0
        tls = False
        connect_timeout = 3000
        _, server_bootstrap, tls_connection_options, socket_options = self.init(host_name, port, tls, connect_timeout)

        server = http.HttpServer.new_server(server_bootstrap, host_name, port, socket_options, on_incoming_connection, on_destroy_complete)
        print("----Server create success----")
        future = http.HttpServer.release(server)
        print(future.result())

        print("----TEST SERVER_CREATE_DESTROY SUCCESS!----")
        print("\n")
        #delete the socket, cleanup
        os.system("rm {}".format(host_name))
    
    def test_server_connection(self):
        print("----TEST SERVER_CONNECTION BEGIN!----")
        def on_incoming_request(connection):
            print("----fake on incoming request----")

        def on_server_conn_shutdown(connection, error_code):
            print("----shutdown server connection with error_code: {}----".format(error_code))

        def on_incoming_connection(connection, error_code):
            #configure the connection here!
            if(error_code):
                print("----server connection fail with error_code: {}----".format(error_code))
                server_conn_future.set_exception(Exception("Error during connect: err={}".format(error_code)))
            server_connection = http.ServerConnection.new_server_connection(connection, on_incoming_request, on_server_conn_shutdown)
            server_conn_future.set_result("----fake on incoming connection!----")
        
        def on_destroy_complete(server):
            destroy_future.set_result("----destroy completed!----")

        #Init for tests
        host_name = str(random.random())
        port = 0
        tls = False
        connect_timeout = 3000
        event_loop_group, server_bootstrap, tls_connection_options, socket_options = self.init(host_name, port, tls, connect_timeout)

        #server setup
        server_conn_future = Future()
        server = http.HttpServer.new_server(server_bootstrap, host_name, port, socket_options, on_incoming_connection, on_destroy_complete)
        print("----server setup completed!----")
        #client setup
        # invoked up on the connection closing
        def on_connection_shutdown(err_code):
            print('----connection close with error code {}----'.format(err_code))

        # client bootstrap knows how to connect all the pieces. In this case it also has the default dns resolver
        # baked in.
        client_bootstrap = io.ClientBootstrap(event_loop_group)
        print("----MAKE NEW CONNECTION NOW-----")
        connect_future = http.HttpClientConnection.new_connection(client_bootstrap, host_name, port, socket_options,
                                                                on_connection_shutdown, tls_connection_options)
        connection = connect_future.result()
        self.assertIsNotNone(connection)
        #wait for server connection setup
        print(server_conn_future.result())
        
        #release the server
        destroy_future = http.HttpServer.release(server)
        print(destroy_future.result())

        print("----TEST SERVER_CONNECTION SUCCESS!----")
        print("\n")
        #delete the socket, cleanup
        os.system("rm {}".format(host_name))
        
if __name__ == '__main__':
    unittest.main()

# server bootstrap init

