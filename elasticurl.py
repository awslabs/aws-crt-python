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
from __future__ import print_function
import argparse
import sys
import os
from io import BytesIO, open  # Python2's built-in open() doesn't return a stream
from awscrt import io, http
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse


def print_header_list(headers):
    for name, value in headers:
        print('{}: {}'.format(name, value))


parser = argparse.ArgumentParser()
parser.add_argument('url', help='URL to make request to. HTTPS is assumed unless port 80 is specified or HTTP is specified in the scheme.')
parser.add_argument('--cacert', required=False, help='FILE: path to a CA certificate file.')
parser.add_argument('--capath', required=False, help='PATH: path to a directory containing CA files.')
parser.add_argument('--cert', required=False, help='FILE: path to a PEM encoded certificate to use with mTLS')
parser.add_argument('--key', required=False, help='FILE: Path to a PEM encoded private key that matches cert.')
parser.add_argument('--connect_timeout', required=False, type=int, help='INT: time in milliseconds to wait for a connection.', default=3000)
parser.add_argument('-H', '--header', required=False, help='STRING: line to send as a header in format "name:value". May be specified multiple times.', action='append')
parser.add_argument('-d', '--data', required=False, help='STRING: Data to POST or PUT.')
parser.add_argument('--data_file', required=False, help='FILE: File to read from file and POST or PUT')
parser.add_argument('-M', '--method', required=False, help='STRING: Http Method verb to use for the request', default='GET')
parser.add_argument('-G', '--get', required=False, help='uses GET for the verb', action='store_true')
parser.add_argument('-P', '--post', required=False, help='uses POST for the verb', action='store_true')
parser.add_argument('-I', '--head', required=False, help='uses HEAD for the verb', action='store_true')
parser.add_argument('-i', '--include', required=False, help='Includes headers in output', action='store_true', default=False)
parser.add_argument('-k', '--insecure', required=False, help='Turns off x.509 validation', action='store_true', default=False)
parser.add_argument('-o', '--output', required=False, help='FILE: dumps content-body to FILE instead of stdout.')
parser.add_argument('-t', '--trace', required=False, help='FILE: dumps logs to FILE instead of stderr.')
parser.add_argument('-p', '--alpn', required=False, help='STRING: protocol for ALPN. May be specified multiple times.', action='append')
parser.add_argument('-v', '--verbose', required=False, help='ERROR|INFO|DEBUG|TRACE: log level to configure. Default is none.')

args = parser.parse_args()

output = getattr(sys.stdout, 'buffer', sys.stdout)

if args.output:
    output = open(args.output, mode='wb')

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

# an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
# you only want one of these.
event_loop_group = io.EventLoopGroup(1)

 # client bootstrap knows how to connect all the pieces. In this case it also has the default dns resolver
# baked in.
client_bootstrap = io.ClientBootstrap(event_loop_group)

url = urlparse(args.url)
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

if scheme == 'https':
    if args.cert is not None and args.key is not None:
        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(args.cert, args.key)
    else:
        tls_ctx_options = io.TlsContextOptions()

    if args.cacert is not None or args.capath is not None:
        tls_ctx_options.override_default_trust_store_from_path(args.capath, args.cacert)

    if args.insecure:
        tls_ctx_options.verify_peer = False

    tls_ctx = io.ClientTlsContext(tls_ctx_options)

    tls_connection_options = tls_ctx.new_connection_options()
    tls_connection_options.set_server_name(url.hostname)

    if args.alpn:
        tls_connection_options.set_alpn_list(args.alpn)

# invoked up on the connection closing
def on_connection_shutdown(shutdown_future):
    print('connection close with error: {}'.format(shutdown_future.exception()))


# invoked by the http request call as the response body is received in chunks
def on_incoming_body(http_stream, body_data):
    output.write(body_data)


data_len = 0
data_stream = None

if args.data:
    data_bytes = args.data.encode(encoding='utf-8')
    data_len = len(data_bytes)
    data_stream = BytesIO(data_bytes)
elif args.data_file:
    data_len = os.stat(args.data_file).st_size
    data_stream = open(args.data_file, 'rb')


socket_options = io.SocketOptions()
socket_options.connect_timeout_ms = args.connect_timeout

hostname = url.hostname
connect_future = http.HttpClientConnection.new(hostname, port, socket_options,
                                               tls_connection_options, client_bootstrap)
connection = connect_future.result(10)
connection.shutdown_future.add_done_callback(on_connection_shutdown)

request = http.HttpRequest(args.method, body_stream=data_stream)

if args.get:
    request.method = "GET"

if args.post:
    request.method = "POST"

if args.head:
    request.method = "HEAD"

if url.path:
    request.path = url.path

if url.query:
    request.path += '?' + url.query

request.headers.add('host', hostname)
request.headers.add('user-agent', 'elasticurl.py 1.0, Powered by the AWS Common Runtime.')

if data_len != 0:
    request.headers.add('content-length', str(data_len))

if args.header:
    for i in args.header:
        name, value = i.split(':')
        request.headers.add(name.strip(), value.strip())

# invoked as soon as the response headers are received
def response_received_cb(http_stream, status_code, headers):
    if args.include:
        print('Response Code: {}'.format(status_code))
        print_header_list(headers)


# make the request
stream = connection.request(request, response_received_cb, on_incoming_body)

# wait until the full response is finished
stream.completion_future.result()
stream = None
connection = None

if data_stream:
    data_stream.close()

if args.output:
    output.close()
