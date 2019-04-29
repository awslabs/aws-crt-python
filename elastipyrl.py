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
from awscrt import io, http
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument('url', help='URL to make request to. HTTPS is assumed unless port 80 is specified or HTTP is specified in the scheme.')
parser.add_argument('--cacert', required=False, help='FILE: path to a CA certficate file.')
parser.add_argument('--capath', required=False, help='PATH: path to a directory containing CA files.')
parser.add_argument('--cert', required=False, help='FILE: path to a PEM encoded certificate to use with mTLS')
parser.add_argument('--key', required=False, help='FILE: Path to a PEM encoded private key that matches cert.')
parser.add_argument('--connect_timeout', required=False, type=int, help='INT: time in milliseconds to wait for a connection.', default=3000)
parser.add_argument('-H', '--header', required=False, help='INT: time in milliseconds to wait for a connection.')
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
parser.add_argument('-p', '--alpn_list', required=False, help='STRING: List of protocols for ALPN, semi-colon delimited')
parser.add_argument('-v', '--verbose', required=False, help='ERROR|INFO|DEBUG|TRACE: log level to configure. Default is none.')

args = parser.parse_args()

# an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
# you only want one of these.
event_loop_group = io.EventLoopGroup(1)

# client bootstrap knows how to connect all the pieces. In this case it also has the default dns resolver
# baked in.
client_bootstrap = io.ClientBootstrap(event_loop_group)

url = urlparse(args.url)
port = 443
print(args)
if url.port is not None:
    port = url.port

tls_connection_options = None

if url.scheme == 'http' or port == 80 or port == 8080:
    pass
else:
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

    if args.alpn_list:
        tls_connection_options.set_alpn_list(args.alpn_list)

method = args.method

if args.get:
    method = 'GET'

if args.post:
    method = 'POST'

if args.head:
    method = 'HEAD'


def on_connection_shutdown(err_code):
    pass


def on_incoming_body(body_data):
    print(body_data)


def on_outgoing_body(request_body_buf):
    return -1


socket_options = io.SocketOptions()
socket_options.connect_timeout_ms = args.connect_timeout

connect_future = http.HttpClientConnection.new_connection(client_bootstrap, url.hostname, port, socket_options,
                                                          on_connection_shutdown, tls_connection_options)

connection = connect_future.result()

outgoing_headers = {'host': url.hostname}

uri_str = url.path

if uri_str is None or uri_str == '':
    uri_str = '/'

if url.query is not None:
    uri_str += url.query

print(uri_str)
request = http.HttpRequest(method, uri_str, outgoing_headers, on_outgoing_body, on_incoming_body)

response_start_future = connection.make_request(request)
response_start = response_start_future.result()

if args.include:
    print(request.response_headers)

response_finished = request.response_completed.result()
connection.close()

request = None
connection = None
