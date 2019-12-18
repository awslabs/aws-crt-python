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

from __future__ import absolute_import, print_function
import awscrt.http
import awscrt.io
import enum
import sys

# Application for use with the test_appexit unit tests.
# Performs an HTTP request and shuts everything down,
# with the opportunity to exit the application at any stage.

Stage = enum.Enum('Stage', [
    'Start',
    'EventLoopGroupStart',
    'HostResolverStart',
    'ClientBootstrapStart',
    'TlsConnectionOptionsStart',
    'HttpClientStart',
    'HttpClientConnected',
    'HttpStreamStart',
    'HttpStreamReceivingBody',
    'HttpStreamDone',
    'HttpConnectionClose',
    'HttpConnectionDone',
    'TlsConnectionOptionsDone',
    'ClientBootstrapDone',
    'HostResolverDone',
    'EventLoopGroupDone',
    'Done',
])


EXIT_STAGE = Stage.Done
TIMEOUT = 10.0
REQUEST_HOST = 's3.amazonaws.com'
REQUEST_PATH = '/code-sharing-aws-crt/elastigirl.png'
REQUEST_PORT = 443


def set_stage(stage):
    print("Stage:", stage)
    if stage.value >= EXIT_STAGE.value:
        print("Exiting now")
        sys.exit()


if __name__ == '__main__':
    EXIT_STAGE = Stage[sys.argv[1]]

    awscrt.io.init_logging(awscrt.io.LogLevel.Trace, 'stdout')

    set_stage(Stage.Start)

    # EventLoopGroupStart
    elg = awscrt.io.EventLoopGroup()
    set_stage(Stage.EventLoopGroupStart)

    # HostResolverStart
    resolver = awscrt.io.DefaultHostResolver(elg)
    set_stage(Stage.HostResolverStart)

    # ClientBootstrapStart
    bootstrap = awscrt.io.ClientBootstrap(elg, resolver)
    set_stage(Stage.ClientBootstrapStart)

    # TlsConnectionOptionsStart
    tls_ctx_opt = awscrt.io.TlsContextOptions()
    tls_ctx = awscrt.io.ClientTlsContext(tls_ctx_opt)
    tls_conn_opt = tls_ctx.new_connection_options()
    tls_conn_opt.set_server_name(REQUEST_HOST)
    set_stage(Stage.TlsConnectionOptionsStart)

    # HttpClientStart
    connection_future = awscrt.http.HttpClientConnection.new(
        host_name=REQUEST_HOST,
        port=REQUEST_PORT,
        bootstrap=bootstrap,
        tls_connection_options=tls_conn_opt)
    set_stage(Stage.HttpClientStart)

    # HttpClientConnected
    http_connection = connection_future.result(TIMEOUT)
    set_stage(Stage.HttpClientConnected)

    # HttpStreamStart
    request = awscrt.http.HttpRequest(path=REQUEST_PATH)
    request.headers.add('Host', REQUEST_HOST)

    def on_incoming_body(http_stream, chunk):
        set_stage(Stage.HttpStreamReceivingBody)

    http_stream = http_connection.request(request, on_body=on_incoming_body)
    set_stage(Stage.HttpStreamStart)

    # HttpStreamDone
    status_code = http_stream.completion_future.result(TIMEOUT)
    assert(status_code == 200)
    del http_stream
    set_stage(Stage.HttpStreamDone)

    # HttpConnectionClose
    shutdown_future = http_connection.close()
    set_stage(Stage.HttpConnectionClose)

    # HttpConnectionDone
    del http_connection
    shutdown_future.result(TIMEOUT)
    set_stage(Stage.HttpConnectionDone)

    # TlsConnectionOptionsDone
    del tls_conn_opt
    del tls_ctx
    del tls_ctx_opt
    set_stage(Stage.TlsConnectionOptionsDone)

    # ClientBootstrapDone
    shutdown_event = bootstrap.shutdown_event
    del bootstrap
    shutdown_event.wait(TIMEOUT)
    set_stage(Stage.ClientBootstrapDone)

    # HostResolverDone
    del resolver
    set_stage(Stage.HostResolverDone)

    # EventLoopGroupDone
    shutdown_event = elg.shutdown_event
    del elg
    shutdown_event.wait(TIMEOUT)
    set_stage(Stage.EventLoopGroupDone)

    # Done
    set_stage(Stage.Done)
