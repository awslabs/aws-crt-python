# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.http import HttpHeaders, HttpRequest
from awscrt.s3_client import S3Client, AwsS3RequestType, S3Request
from test import NativeResourceTest, TIMEOUT
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, init_logging, LogLevel
from awscrt.auth import AwsCredentialsProvider
import io
import unittest


def S3ClientNew(secure, region):

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
        tls_connection_options=tls_option)

    return s3_client


class S3ClientTest(NativeResourceTest):
    region = "us-west-2"
    timeout = 10  # seconds

    def test_sanity(self):
        s3_client = S3ClientNew(False, self.region)
        self.assertIsNotNone(s3_client)

    def test_sanity_secure(self):
        s3_client = S3ClientNew(True, self.region)
        self.assertIsNotNone(s3_client)

    def test_wait_shutdown(self):
        s3_client = S3ClientNew(False, self.region)
        self.assertIsNotNone(s3_client)
        shutdown_future = s3_client.shutdown_future
        del s3_client
        self.assertIsNone(shutdown_future.result(self.timeout))


class S3RequestTest(NativeResourceTest):
    test_object_path = "/get_object_test_1MB.txt"
    region = "us-west-2"
    bucket_name = "aws-crt-canary-bucket"
    timeout = 10  # seconds

    def _build_endpoint_string(self, region, bucket_name):
        return bucket_name + ".s3." + region + ".amazonaws.com"

    def _get_object_request(self):
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name))])
        request = HttpRequest("GET", self.test_object_path, headers)
        return request

    def _on_request_headers(self, status_code, headers, **kargs):
        print(status_code)
        self.assertEqual(status_code, 200, "status code is not 200")
        self.assertIsNotNone(headers, "headers are none")

    def _on_request_body(self, chunk, ** kargs):
        self.assertIsNotNone(chunk, "the body chunk is none")

    def test_get_object(self):
        init_logging(LogLevel.Trace, "log.txt")
        s3_client = S3ClientNew(False, self.region)
        request = self._get_object_request()
        s3_request = S3Request(
            client=s3_client,
            request=request,
            type=AwsS3RequestType.GET_OBJECT,
            on_headers=self._on_request_headers,
            on_body=self._on_request_body)
        finished_future = s3_request.finished_future
        result = (finished_future.result(self.timeout))
        print(result)
        shutdown_future = s3_request.shutdown_future
        del s3_request
        result = (shutdown_future.result(self.timeout))
        print(result)
        del s3_client
        self.assertIsNone(s3_client.shutdown_future.result(self.timeout))
