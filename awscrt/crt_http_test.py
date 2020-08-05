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
import argparse
import threading

#Create lock and event for globals
lock = threading.Lock()
event = threading.Event()

#Parse command line arguments for http request options
parser = argparse.ArgumentParser()
parser.add_argument('-G', '--GET', required=False, help='uses GET for the verb', action='store_true')
parser.add_argument('-P', '--PUT', required=False, help='uses PUT for the verb', action='store_true')
parser.add_argument('-t', '--numTransfers', required=False, help='number of transfers')
parser.add_argument('-f', '--file_size', required=False, help='file size')
parser.add_argument('--https', required=False, help='enable https')
args = parser.parse_args()
transfers_left = int(args.numTransfers)


obj_number = 9223372036854775806
#credentials    
access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
session_token = os.environ.get('AWS_SESSION_TOKEN')
credentials_provider = AwsCredentialsProvider.new_static(access_key_id, secret_access_key, session_token)

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
#to get byte size multiply b'a' by target size - 121
    stream_size = obj_size - 121
    body_stream = io.BytesIO(b'a' * stream_size)
    headers.add("Content-Length", str(stream_size))
    request = HttpRequest(method="PUT", path=("/" + key), headers=headers, body_stream=body_stream)
    return request

#Return Get Request
def get_request(key, headers):
    request = HttpRequest("GET", "/" + key, headers=headers)
    return request

#Http Stream Complete Callback 
def on_stream_complete(stream_future):
    try:
        stream_result = stream_future.result()
        print("Http Response Code: ", stream_result)
        with lock:
            global transfers_left
            print("transfers_left", transfers_left)
            transfers_left -= 1
            if transfers_left == 0:
                event.set()
    except Exception as e:
        print("Exception: ", e)
        event.set()
        exit(-1)

#Http Connection Callback
def on_connection(connection_future):
    try: 
        connection = connection_future.result()        
        key = "crt-canary-obj-single-part-"
        cp = None
        obj_key = None
        get = False
        put = False
        #access object key and credentials provider
        with lock:
            global obj_number
            obj_key = key  + str(obj_number)
            obj_number -= 1
            global credentials_provider
            cp = credentials_provider           
            global args
            if args.GET:
                get = True
            if args.PUT:
                put = True
                

        #set up sign config
        date = datetime.datetime.now(datetime.timezone.utc)
        signing_config = AwsSigningConfig(algorithm=AwsSigningAlgorithm.V4, signature_type=AwsSignatureType.HTTP_REQUEST_HEADERS, credentials_provider=cp, 
        region="us-east-2", service="s3", date=date, should_sign_header=None, use_double_uri_encode=False,
            should_normalize_uri_path=False,
            signed_body_value_type=awscrt.auth.AwsSignedBodyValueType.UNSIGNED_PAYLOAD,
            signed_body_header_type=awscrt.auth.AwsSignedBodyHeaderType.X_AMZ_CONTENT_SHA_256,
            expiration_in_seconds=120,
            omit_session_token=False)
    
#make request
        headers = HttpHeaders([("content-type", "text/plain"), ("host", connection.host_name)]) 
        request = HttpRequest()

        if get:
            request = get_request(obj_key, headers)
        if put:
            request = put_request(obj_key, headers, int(args.file_size))

        signed_request_future = awscrt.auth.aws_sign_request(request, signing_config)
        signed_request_result = signed_request_future.result(10.0)

        response = Response()
        
        http_client_stream = connection.request(signed_request_result, response.on_response, response.on_body)
        http_client_stream.activate()

# Process stream results in callback
        http_client_stream.completion_future.add_done_callback(on_stream_complete)

    except Exception as e:
        print("Exception: ", e)
        event.set()
        exit(-1)

#args order
# 0 - program name
# 1 - num transfers
# 2 - file size
# 3 - get / put
def main():

    _awscrt.trace_event_begin("Python-http", "Main()")

    host_name = "crt-canary-bucket-ramosth.s3.us-east-2.amazonaws.com"
    port = 80
    start = time.time()
    #start event loop and client bootstrap
    event_loop_group = EventLoopGroup(0)
    host_resolver = DefaultHostResolver(event_loop_group)
    client_bootstrap = ClientBootstrap(event_loop_group, host_resolver)
    for i in range(int(args.numTransfers)):
        HttpClientConnection.new(host_name=host_name, port=port, bootstrap=client_bootstrap).add_done_callback(on_connection)
        print("Transfer Number: ", i, " initiated")
    event.wait()
    end = time.time()
    total = end - start
    print("Time to complete in seconds: ", total)
    _awscrt.trace_event_end("Python-http", "Main()")


if __name__ == "__main__":
    main()
