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

parser = argparse.ArgumentParser()
parser.add_argument('--host_name', required=False, help='String: The host name for the server. Default is \"local_host\"', default = "local_host")
parser.add_argument('--port', required=False, help='Int: The port number for the server. Default is 0', default = 0)
parser.add_argument('--tls', required=False, help='Bool: Create a tls server or a simple server. Default is false', default = False)
parser.add_argument('--connect_timeout', required=False, type=int, help='INT: time in milliseconds to wait for a connection.', default=3000)
parser.add_argument('-v', '--verbose', required=False, help='ERROR|INFO|DEBUG|TRACE: log level to configure. Default is none.')
parser.add_argument('-t', '--trace', required=False, help='FILE: dumps logs to FILE instead of stderr.')
parser.add_argument('-o', '--output', required=False, help='FILE: dumps content-body to FILE instead of stdout.')

args = parser.parse_args()
# setup the logger if user request logging

if args.verbose:
    log_level = io.LogLevel.NoLogs

    if args.verbose == 'ERROR':
        log_level = io.LogLevel.Error
    elif args.verbose == 'INFO':
        log_level = io.LogLevel.Info
    elif args.verbose == 'DEBUG':
        log_level = io.LogLevel.Debug
    elif args.verbose == 'TRACE':
        log_level = io.LogLevel.Trace
    else:
        print('{} unsupported value for the verbose option'.format(args.verbose))
        exit(-1)

    log_output = 'stderr'

    if args.trace:
        log_output = args.trace

    io.init_logging(log_level, log_output)


if sys.platform == 'win32':
    #win32
    host_name = "\\\\.\\pipe\\testsock-" + args.host_name
else:
    host_name = "testsock-{}.sock".format(args.host_name)
port = args.port

# an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
# you only want one of these.
event_loop_group = io.EventLoopGroup(1)

# server bootstrap init
server_boostrap = io.ServerBoostrap(event_loop_group)

socket_options = io.SocketOptions()
socket_options.connect_timeout_ms = args.connect_timeout
socket_options.domain = io.SocketDomain.Local

def on_incoming_connection(server, connection, error_code):
    print("fake on incoming connection!")

def on_destroy_complete(server):
    future.set_result("destroy completed!")

server = http.HttpServer.new_server(server_boostrap, host_name, port, socket_options, on_incoming_connection, on_destroy_complete)

future = http.HttpServer.release(server)
print(future.result())

print("SUCCESS!")
#delete the socket, cleanup
os.system("rm {}".format(host_name))
