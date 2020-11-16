# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.http import HttpHeaders, HttpRequest
from awscrt.s3_client import S3Client, AwsS3RequestType
from test import NativeResourceTest, TIMEOUT
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
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

    def _build_endpoint_string(self, region, bucket_name):
        return bucket_name + ".s3" + region + ".amazonaws.com"

    def _get_object_request(self):
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name))])
        request = HttpRequest("GET", self.test_object_path, headers)
        return request

    def test_get_object(self):
        s3_client = S3ClientNew(False, self.region)
        request = self._get_object_request()
        S3_request = s3_client.make_request(request=request, type=AwsS3RequestType.GET_OBJECT)
