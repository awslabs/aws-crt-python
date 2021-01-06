# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.http import HttpHeaders, HttpRequest
from awscrt.s3 import S3Client, S3RequestType
from test import NativeResourceTest
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from awscrt.auth import AwsCredentialsProvider
import unittest
import os
from tempfile import NamedTemporaryFile


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

        shutdown_event = s3_client.shutdown_event
        del s3_client
        self.assertTrue(shutdown_event.wait(self.timeout))


class S3RequestTest(NativeResourceTest):
    get_test_object_path = "/get_object_test_10MB.txt"
    put_test_object_path = "/put_object_test_py_10MB.txt"
    region = "us-west-2"
    bucket_name = "aws-crt-canary-bucket"
    timeout = 100  # seconds
    num_threads = 0

    response_headers = None
    response_status_code = None
    received_body_len = 0
    transferred_len = 0
    data_len = 0

    put_body_stream = None

    def _build_endpoint_string(self, region, bucket_name):
        return bucket_name + ".s3." + region + ".amazonaws.com"

    def _get_object_request(self, object_path):
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name))])
        request = HttpRequest("GET", object_path, headers)
        return request

    def _put_object_request(self, file_name):
        self.put_body_stream = open(file_name, "r+b")
        file_stats = os.stat(file_name)
        self.data_len = file_stats.st_size
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name)),
                               ("Content-Type", "text/plain"), ("Content-Length", str(self.data_len))])
        request = HttpRequest("PUT", self.put_test_object_path, headers, self.put_body_stream)
        return request

    def _on_request_headers(self, status_code, headers, **kargs):
        self.response_status_code = status_code
        self.response_headers = headers

    def _on_request_body(self, chunk, offset, **kargs):
        self.received_body_len = self.received_body_len + len(chunk)

    def _on_progress(self, progress):
        self.transferred_len += progress

    def _validate_successful_get_response(self, put_object):
        self.assertEqual(self.response_status_code, 200, "status code is not 200")
        headers = HttpHeaders(self.response_headers)
        self.assertIsNone(headers.get("Content-Range"))
        body_length = headers.get("Content-Length")
        if not put_object:
            self.assertIsNotNone(body_length, "Content-Length is missing from headers")
        if body_length:
            self.assertEqual(
                int(body_length),
                self.received_body_len,
                "Received body length does not match the Content-Length header")

    def _test_s3_put_get_object(self, request, type):
        s3_client = s3_client_new(False, self.region, 5 * 1024 * 1024)
        s3_request = s3_client.make_request(
            request=request,
            type=type,
            on_headers=self._on_request_headers,
            on_body=self._on_request_body)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)
        self._validate_successful_get_response(type is S3RequestType.PUT_OBJECT)
        shutdown_event = s3_request.shutdown_event
        del s3_request
        self.assertTrue(shutdown_event.wait(self.timeout))

    def test_get_object(self):
        request = self._get_object_request(self.get_test_object_path)
        self._test_s3_put_get_object(request, S3RequestType.GET_OBJECT)

    def test_put_object(self):
        request = self._put_object_request("test/resources/s3_put_object.txt")
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT)
        self.put_body_stream.close()

    def test_get_object_file_object(self):
        request = self._get_object_request(self.get_test_object_path)
        type = S3RequestType.GET_OBJECT
        s3_client = s3_client_new(False, self.region, 5 * 1024 * 1024)
        with NamedTemporaryFile("w") as file:
            s3_request = s3_client.make_request(
                request=request,
                file=file.name,
                type=type,
                on_headers=self._on_request_headers,
                on_progress=self._on_progress)
            finished_future = s3_request.finished_future
            finished_future.result(self.timeout)

            # Result check
            self.data_len = int(HttpHeaders(self.response_headers).get("Content-Length"))
            self.assertEqual(
                self.data_len,
                self.transferred_len,
                "the transferred length reported does not match the content-length header")
            self.assertEqual(self.response_status_code, 200, "status code is not 200")
            shutdown_event = s3_request.shutdown_event
            del s3_request
            self.assertTrue(shutdown_event.wait(self.timeout))
            # TODO verify the written file

    def _on_progress_cancel_after_first_chunk(self, progress):
        self.transferred_len += progress
        self.s3_request.cancel()

    def test_multipart_get_object_cancel(self):
        # a 5 GB file
        request = self._get_object_request("/crt-canary-obj-single-part-9223372036854775807")
        type = S3RequestType.GET_OBJECT
        s3_client = s3_client_new(False, self.region, 5 * 1024 * 1024)
        with NamedTemporaryFile("w") as file:
            self.s3_request = s3_client.make_request(
                request=request,
                file=file.name,
                type=type,
                on_headers=self._on_request_headers,
                on_progress=self._on_progress_cancel_after_first_chunk)
            finished_future = self.s3_request.finished_future
            try:
                finished_future.result(10)
            except Exception:
                pass

            # Result check
            self.data_len = int(HttpHeaders(self.response_headers).get("Content-Length"))
            self.assertLess(
                self.transferred_len,
                self.data_len,
                "the transferred length reported does not match the content-length header")
            self.assertEqual(self.response_status_code, 200, "status code is not 200")
            shutdown_event = self.s3_request.shutdown_event
            del self.s3_request
            self.assertTrue(shutdown_event.wait(self.timeout))
            # TODO verify the written file

    def test_put_object_file_object(self):
        request = self._put_object_request("test/resources/s3_put_object.txt")
        type = S3RequestType.PUT_OBJECT
        # close the stream, to test if the C FILE pointer as the input stream working well.
        self.put_body_stream.close()
        s3_client = s3_client_new(False, self.region, 5 * 1024 * 1024)
        s3_request = s3_client.make_request(
            request=request,
            file="test/resources/s3_put_object.txt",
            type=type,
            on_headers=self._on_request_headers,
            on_progress=self._on_progress)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)

        # check result
        self.assertEqual(
            self.data_len,
            self.transferred_len,
            "the transferred length reported does not match body we sent")
        self._validate_successful_get_response(type is S3RequestType.PUT_OBJECT)
        shutdown_event = s3_request.shutdown_event
        del s3_request
        self.assertTrue(shutdown_event.wait(self.timeout))


if __name__ == '__main__':
    unittest.main()
