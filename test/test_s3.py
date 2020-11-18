# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.http import HttpHeaders, HttpRequest
from awscrt.s3_client import S3Client, AwsS3RequestType, S3Request
from test import NativeResourceTest, TIMEOUT
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, init_logging, LogLevel
from awscrt.auth import AwsCredentialsProvider
import io
import unittest
import os


def s3_client_new(secure, region, part_size=0):

    event_loop_group = EventLoopGroup()
    host_resolver = DefaultHostResolver(event_loop_group)
    bootstrap = ClientBootstrap(event_loop_group, host_resolver)
    credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
    tls_option = None
    if secure:
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)
        tls_option = TlsConnectionOptions(ctx)

    s3_client = S3Client(
        bootstrap=bootstrap,
        region=region,
        credential_provider=credential_provider,
        tls_connection_options=tls_option,
        part_size=part_size)

    return s3_client


class S3ClientTest(NativeResourceTest):
    region = "us-west-2"
    timeout = 10  # seconds

    def test_sanity(self):
        s3_client = s3_client_new(False, self.region)
        self.assertIsNotNone(s3_client)

    def test_sanity_secure(self):
        s3_client = s3_client_new(True, self.region)
        self.assertIsNotNone(s3_client)

    def test_wait_shutdown(self):
        s3_client = s3_client_new(False, self.region)
        self.assertIsNotNone(s3_client)
        shutdown_future = s3_client.shutdown_future
        del s3_client
        self.assertIsNone(shutdown_future.result(self.timeout))


class S3RequestTest(NativeResourceTest):
    test_object_path = "/get_object_test_1MB.txt"
    region = "us-west-2"
    bucket_name = "aws-crt-canary-bucket"
    timeout = 10  # seconds
    num_threads = 0

    response_headers = None
    response_status_code = None
    body_len = 0

    def _build_endpoint_string(self, region, bucket_name):
        return bucket_name + ".s3." + region + ".amazonaws.com"

    def _get_object_request(self):
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name))])
        request = HttpRequest("GET", self.test_object_path, headers)
        return request

    def _on_request_headers(self, status_code, headers, **kargs):

        self.assertEqual(status_code, 200, "status code is not 200")
        self.assertIsNotNone(headers, "headers are none")
        self.response_headers = headers

    def _on_request_body(self, chunk, **kargs):
        self.assertIsNotNone(chunk, "the body chunk is none")
        self.body_len = self.body_len + len(chunk)

    def _validate_successful_response(self):
        error = False
        error |= self.response_status_code != 200
        return not error

    def _download_file_example(self):
        # num_threads is the Number of event-loops to create. Pass 0 to create one for each processor on the machine.
        event_loop_group = EventLoopGroup(self.num_threads)
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
        s3_client = S3Client(
            bootstrap=bootstrap,
            region="us-west-2",
            credential_provider=credential_provider)
        headers = HttpHeaders([("host", self.bucket_name + ".s3." + self.region + ".amazonaws.com")])
        request = HttpRequest("GET", "/get_object_test_1MB.txt", headers)
        file = open("get_object_test_1MB.txt", "wb")

        def on_body(chunk):
            file.write(chunk)

        s3_request = s3_client.make_request(
            request=request,
            type=AwsS3RequestType.GET_OBJECT,
            on_body=on_body)
        finished_future = s3_request.finished_future
        result = finished_future.result(self.timeout)
        file.close()

    def _upload_file_example(self):
        # num_threads is the Number of event-loops to create. Pass 0 to create one for each processor on the machine.
        init_logging(LogLevel.Trace, "log.txt")
        event_loop_group = EventLoopGroup(self.num_threads)
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
        s3_client = S3Client(
            bootstrap=bootstrap,
            region="us-west-2",
            credential_provider=credential_provider)
        data_len = os.stat("put_object_test_10MB.txt").st_size
        print(data_len)
        data_stream = open("put_object_test_10MB.txt", 'rb')
        headers = HttpHeaders([("host", self.bucket_name + ".s3." + self.region +
                                ".amazonaws.com"), ("Content-Type", "text/plain"), ("Content-Length", str(data_len))])
        request = HttpRequest("PUT", "/put_object_test_10MB.txt", headers, data_stream)

        def on_headers(status_code, headers):
            print(status_code)
            print(headers)
        s3_request = s3_client.make_request(
            request=request,
            type=AwsS3RequestType.PUT_OBJECT,
            on_headers=on_headers
        )
        finished_future = s3_request.finished_future
        result = finished_future.result(self.timeout)
        data_stream.close()

    def test_get_object(self):
        s3_client = s3_client_new(False, self.region, 16 * 1024)
        request = self._get_object_request()
        s3_request = s3_client.make_request(
            request=request,
            type=AwsS3RequestType.GET_OBJECT,
            on_headers=self._on_request_headers,
            on_body=self._on_request_body)
        finished_future = s3_request.finished_future
        result = (finished_future.result(self.timeout))
        print(result)
        print(self.response_headers)
        print(self.body_len)

    # def test_sample(self):
    #     self._upload_file_example()

    # def test_put_object(self):
    #     s3_client = s3_client_new(False, self.region, 16 * 1024)
    #     request = self._put_object_request()
    #     s3_request = s3_client.make_request(
    #         request=request,
    #         type=AwsS3RequestType.GET_OBJECT,
    #         on_headers=self._on_request_headers,
    #         on_body=self._on_request_body)
    #     finished_future = s3_request.finished_future
    #     result = (finished_future.result(self.timeout))
    #     print(result)
    #     print(self.response_headers)
    #     print(self.body_len)
