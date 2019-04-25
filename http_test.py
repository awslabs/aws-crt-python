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
from awscrt import io, http


def on_client_connection_shutdown(error_code):
    print("Connection has been shutdown with error_code ", error_code)


parser = argparse.ArgumentParser()
parser.add_argument('--url', required=True, help="Url to download from")
parser.add_argument('--output', required=True, help="Location to write file")

args = parser.parse_args()

while True:
    # Run
    event_loop_group = io.EventLoopGroup(1)
    client_bootstrap = io.ClientBootstrap(event_loop_group)
    tls_options = io.TlsContextOptions()
    tls_options.verify_peer = False
    port = 443

    tls_context = io.ClientTlsContext(tls_options)

    tls_conn_options = tls_context.new_connection_options()
    tls_conn_options.set_server_name("s3.amazonaws.com")
    socket_options = io.SocketOptions()

    connect_result = http.HttpClientConnection.new_connection(client_bootstrap, 's3.amazonaws.com', 443, socket_options,
                                                              on_client_connection_shutdown, tls_conn_options).result()
    print('connection finished')
    print('connection is open? ', connect_result.is_open())
    connect_result.close()
    print('connection is open? ', connect_result.is_open())

    print('please do not be deleted yet.')
    connect_result = None
