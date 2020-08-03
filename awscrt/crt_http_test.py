#Copyright Amazon.com, Inc.or its affiliates.All Rights Reserved.
#SPDX - License - Identifier : Apache - 2.0.

from __future__ import absolute_import
import _awscrt 
from concurrent.futures import Future
from awscrt import NativeResource, isinstance_str
import awscrt.exceptions
from awscrt.http import HttpClientConnection, HttpClientStream, HttpHeaders, HttpProxyOptions, HttpRequest, HttpVersion
from awscrt.io import ClientBootstrap, EventLoopGroup, DefaultHostResolver, InputStream, TlsConnectionOptions, SocketOptions
from awscrt.auth import AwsCredentials, AwsCredentialsProvider, AwsSignatureType, AwsSigningAlgorithm, AwsSigningConfig, AwsSignedBodyHeaderType, AwsSignedBodyValueType
from enum import IntEnum
import io
import os
import sys
import threading
import datetime
import time
#import elasticurl
import argparse
#host name = _bucketName + ".s3." + m_canaryApp.GetOptions().region.c_str() + ".amazonaws.com";
#port = 443 for https and 80 for http
"""
Taken from test_http_client.py
"""
class Response(object):
    """Holds contents of incoming response"""

    def __init__(self):
        self.status_code = None
        self.headers = None
        self.body = bytearray()

    def on_response(self, http_stream, status_code, headers, **kwargs):
        self.status_code = status_code
        self.headers = HttpHeaders(headers)

    def on_body(self, http_stream, chunk, **kwargs):
        self.body.extend(chunk)

#Return put request
def put_request(key, headers, obj_size):
#Set up random bytes for body stream
#to get byte size time b 'a' by target size - 121
    stream_size = obj_size - 121
    body_stream = io.BytesIO(b'a' * stream_size)
    headers.add("Content-Length", str(stream_size))
    request = HttpRequest("PUT", "/" + key, headers=headers, body_stream=body_stream)
    return request

#Return Get Request
def get_request(key, headers):
    request = HttpRequest("GET", "/" + key, headers=headers)
    return request

#args order
# 0 - program name
# 1 - num transfers
# 2 - file size
# 3 - get / put
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-G', '--GET', required=False, help='uses GET for the verb', action='store_true')
    parser.add_argument('-P', '--PUT', required=False, help='uses PUT for the verb', action='store_true')
    parser.add_argument('-t', '--numTransfers', required=False, help='number of transfers')
    parser.add_argument('-f', '--file_size', required=False, help='file size')
    parser.add_argument('--https', required=False, help='enable https')
    args = parser.parse_args()

    _awscrt.trace_event_begin("Python-http", "Main()")
#print("num arguments: ", len(sys.argv))
#print("Arguments List: ", str(sys.argv))
    region = "us-east-2"
    bucket =  "crt-canary-bucket-ramosth"
    host_name = bucket + ".s3." + region + ".amazonaws.com"
    port = 80
    service = "s3"
    obj_number = 9223372036854775806
    key = "crt-canary-obj-single-part-"

#credentials
    
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    session_token = os.environ.get('AWS_SESSION_TOKEN')

#start event loop and client bootstrap
    event_loop_group = EventLoopGroup(0)
    host_resolver = DefaultHostResolver(event_loop_group)
    client_bootstrap = ClientBootstrap(event_loop_group, host_resolver)
    
    credentials_provider = AwsCredentialsProvider.new_static(access_key_id, secret_access_key, session_token)
#Create Socket options
    socket_options = awscrt.io.SocketOptions()
#Stream for tcp and Dgram for UDP
    socket_options.type = awscrt.io.SocketType.Stream
    socket_options.connect_timeout_ms = 3000
    socket_options.domain = awscrt.io.SocketDomain.IPv6
#socket_options.keep_alive = True

    start = time.time()

    for counter in range(int(args.numTransfers)):
#https options
        """
        if args.https:
            tls_ctx_options = awscrt.io.TlsContextOptions()
#!tls_ctx_options.override_default_trust_store_from_path()
            tls_ctx = awscrt.io.ClientTlsContext(tls_ctx_options)
            tls_conn_options = tls_ctx.new_connection_options()
            tls_conn_options.set_server_name(host_name)
        else:
            tls_conn_options = None
        """
        connection_future = HttpClientConnection.new(host_name=host_name, port=port, bootstrap=client_bootstrap, socket_options=socket_options)
        connection = connection_future.result(10.0)
#set up sign config
        date = datetime.datetime.now(datetime.timezone.utc) 
        signing_config = AwsSigningConfig(algorithm=AwsSigningAlgorithm.V4, signature_type=AwsSignatureType.HTTP_REQUEST_HEADERS, credentials_provider=credentials_provider, 
        region=region, service=service, date=date, should_sign_header=None, use_double_uri_encode=False,
            should_normalize_uri_path=False,
            signed_body_value_type=awscrt.auth.AwsSignedBodyValueType.UNSIGNED_PAYLOAD,
            signed_body_header_type=awscrt.auth.AwsSignedBodyHeaderType.X_AMZ_CONTENT_SHA_256,
            expiration_in_seconds=120,
            omit_session_token=False)

#make request

        headers = HttpHeaders([("content-type", "text/plain"), ("host", host_name)])

        
        obj_key = key  + str(obj_number)
        obj_number -= 1
        print(obj_key)
        request = HttpRequest()
        if args.GET:
            request = get_request(obj_key, headers)
        if args.PUT:
            request = put_request(obj_key, headers, int(args.file_size))
        signed_request_future = awscrt.auth.aws_sign_request(request, signing_config)

        signed_request_result = signed_request_future.result(10.0)

        response = Response()
        http_client_stream = connection.request(signed_request_result, response.on_response, response.on_body)
        http_client_stream.activate()
#wait for stream to finish, optional arg is timeout as a float
        stream_result = http_client_stream.completion_future.result(300)
        print("Http Response Code: ", stream_result)
    end = time.time()
    total = end - start
    print("Time to complete in seconds: ", total)
    _awscrt.trace_event_end("Python-http", "Main()")
