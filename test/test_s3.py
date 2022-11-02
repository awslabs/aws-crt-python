# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import unittest
import os
import tempfile
import math
import shutil
from test import NativeResourceTest
from concurrent.futures import Future

from awscrt.http import HttpHeaders, HttpRequest
from awscrt.s3 import S3Client, S3RequestType
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from awscrt.auth import AwsCredentialsProvider

MB = 1024 ** 2
GB = 1024 ** 3


class FileCreator(object):
    def __init__(self):
        self.rootdir = tempfile.mkdtemp()

    def remove_all(self):
        shutil.rmtree(self.rootdir)

    def create_file(self, filename, contents, mode='w'):
        """Creates a file in a tmpdir
        ``filename`` should be a relative path, e.g. "foo/bar/baz.txt"
        It will be translated into a full path in a tmp dir.
        ``mode`` is the mode the file should be opened either as ``w`` or
        `wb``.
        Returns the full path to the file.
        """
        full_path = os.path.join(self.rootdir, filename)
        if not os.path.isdir(os.path.dirname(full_path)):
            os.makedirs(os.path.dirname(full_path))
        with open(full_path, mode) as f:
            f.write(contents)
        return full_path

    def create_file_with_size(self, filename, filesize):
        filename = self.create_file(filename, contents='')
        chunksize = 8192
        with open(filename, 'wb') as f:
            for i in range(int(math.ceil(filesize / float(chunksize)))):
                f.write(b'a' * chunksize)
        return filename

    def append_file(self, filename, contents):
        """Append contents to a file
        ``filename`` should be a relative path, e.g. "foo/bar/baz.txt"
        It will be translated into a full path in a tmp dir.
        Returns the full path to the file.
        """
        full_path = os.path.join(self.rootdir, filename)
        if not os.path.isdir(os.path.dirname(full_path)):
            os.makedirs(os.path.dirname(full_path))
        with open(full_path, 'a') as f:
            f.write(contents)
        return full_path

    def full_path(self, filename):
        """Translate relative path to full path in temp dir.
        f.full_path('foo/bar.txt') -> /tmp/asdfasd/foo/bar.txt
        """
        return os.path.join(self.rootdir, filename)


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


class FakeReadStream(object):
    def __init__(self, read_future):
        self._future = read_future

    def read(self, length):
        fake_string = "x" * length
        fake_data = bytes(fake_string, 'utf-8')
        if not self._future.done():
            self._future.set_result(None)
        return fake_data


@unittest.skipUnless(os.environ.get('AWS_TEST_S3'), 'set env var to run test: AWS_TEST_S3')
class S3ClientTest(NativeResourceTest):

    def setUp(self):
        self.region = "us-west-2"
        self.timeout = 10  # seconds
        super().setUp()

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


@unittest.skipUnless(os.environ.get('AWS_TEST_S3'), 'set env var to run test: AWS_TEST_S3')
class S3RequestTest(NativeResourceTest):
    def setUp(self):
        # TODO: use env-vars to customize how these tests are run, instead of relying on hard-coded values
        self.get_test_object_path = "/get_object_test_10MB.txt"
        self.put_test_object_path = "/put_object_test_py_10MB.txt"
        self.region = "us-west-2"
        self.bucket_name = "aws-crt-canary-bucket"
        self.default_file_path = "test/resources/s3_put_object.txt"
        self.timeout = 100  # seconds
        self.num_threads = 0
        self.non_ascii_file_name = "ÉxÅmple.txt".encode("utf-8")

        self.response_headers = None
        self.response_status_code = None
        self.received_body_len = 0
        self.transferred_len = 0
        self.data_len = 0
        self.progress_invoked = 0

        self.put_body_stream = None

        self.files = FileCreator()
        super().setUp()

    def tearDown(self):
        self.files.remove_all()
        super().tearDown()

    def _build_endpoint_string(self, region, bucket_name):
        return bucket_name + ".s3." + region + ".amazonaws.com"

    def _get_object_request(self, object_path):
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name))])
        request = HttpRequest("GET", object_path, headers)
        return request

    def _put_object_request(self, file_name, path=None):
        # if send file path is set, the body_stream of http request will be ignored (using file handler from C instead)
        self.put_body_stream = open(file_name, "r+b")
        file_stats = os.stat(file_name)
        self.data_len = file_stats.st_size
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name)),
                               ("Content-Type", "text/plain"), ("Content-Length", str(self.data_len))])
        if path is None:
            path = self.put_test_object_path
        request = HttpRequest("PUT", path, headers, self.put_body_stream)
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

    def _test_s3_put_get_object(self, request, request_type, exception_name=None):
        s3_client = s3_client_new(False, self.region, 5 * MB)
        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            on_headers=self._on_request_headers,
            on_body=self._on_request_body)
        finished_future = s3_request.finished_future
        try:
            finished_future.result(self.timeout)
        except Exception as e:
            self.assertEqual(e.name, exception_name)
        else:
            self._validate_successful_get_response(request_type is S3RequestType.PUT_OBJECT)

        shutdown_event = s3_request.shutdown_event
        s3_request = None
        self.assertTrue(shutdown_event.wait(self.timeout))

    def test_get_object(self):
        request = self._get_object_request(self.get_test_object_path)
        self._test_s3_put_get_object(request, S3RequestType.GET_OBJECT)

    def test_put_object(self):
        request = self._put_object_request(self.default_file_path)
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT)
        self.put_body_stream.close()

    def test_put_object_multiple_times(self):
        s3_client = s3_client_new(False, self.region, 5 * MB)
        finished_futures = []
        for i in range(3):
            tempfile = self.files.create_file_with_size("temp_file_{}".format(str(i)), 10 * MB)
            path = "/put_object_test_py_10MB_{}.txt".format(str(i))
            request = self._put_object_request(tempfile, path)
            self.put_body_stream.close()
            s3_request = s3_client.make_request(
                request=request,
                type=S3RequestType.PUT_OBJECT,
                send_filepath=tempfile,
                on_headers=self._on_request_headers,
                on_body=self._on_request_body)
            finished_futures.append(s3_request.finished_future)
            # request keeps connection alive. delete pointer so connection can shut down
            del s3_request
        try:
            for future in finished_futures:
                future.result(self.timeout)
        except Exception as e:
            # failed
            self.assertTrue(False)

        client_shutdown_event = s3_client.shutdown_event
        del s3_client
        self.assertTrue(client_shutdown_event.wait(self.timeout))
        self.put_body_stream.close()

    def test_get_object_file_object(self):
        request = self._get_object_request(self.get_test_object_path)
        request_type = S3RequestType.GET_OBJECT
        s3_client = s3_client_new(False, self.region, 5 * MB)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as file:
            file.close()
            s3_request = s3_client.make_request(
                request=request,
                type=request_type,
                recv_filepath=file.name,
                on_headers=self._on_request_headers,
                on_progress=self._on_progress)
            finished_future = s3_request.finished_future
            finished_future.result(self.timeout)

            # Result check
            self.data_len = int(HttpHeaders(self.response_headers).get("Content-Length"))
            file_stats = os.stat(file.name)
            file_len = file_stats.st_size
            self.assertEqual(
                file_len,
                self.transferred_len,
                "the length of written file does not match the transferred length reported")
            self.assertEqual(
                self.data_len,
                self.transferred_len,
                "the transferred length reported does not match the content-length header")
            self.assertEqual(self.response_status_code, 200, "status code is not 200")
            # TODO verify the content of written file
            os.remove(file.name)

    def test_put_object_file_object(self):
        request = self._put_object_request(self.default_file_path)
        request_type = S3RequestType.PUT_OBJECT
        # close the stream, to test if the C FILE pointer as the input stream working well.
        self.put_body_stream.close()
        s3_client = s3_client_new(False, self.region, 5 * MB)
        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            send_filepath=self.default_file_path,
            on_headers=self._on_request_headers,
            on_progress=self._on_progress)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)

        # check result
        self.assertEqual(
            self.data_len,
            self.transferred_len,
            "the transferred length reported does not match body we sent")
        self._validate_successful_get_response(request_type is S3RequestType.PUT_OBJECT)

    def test_put_object_file_object_move(self):
        # remove the input file when request done
        tempfile = self.files.create_file_with_size("temp_file", 10 * MB)
        request = self._put_object_request(tempfile)
        self.put_body_stream.close()
        s3_client = s3_client_new(False, self.region, 5 * MB)
        request_type = S3RequestType.PUT_OBJECT
        done_future = Future()

        def on_done_remove_file(**kwargs):
            os.remove(tempfile)
            done_future.set_result(None)

        s3_client.make_request(
            request=request,
            type=request_type,
            send_filepath=tempfile,
            on_headers=self._on_request_headers,
            on_progress=self._on_progress,
            on_done=on_done_remove_file)
        done_future.result(self.timeout)

        # check result
        self.assertEqual(
            self.data_len,
            self.transferred_len,
            "the transferred length reported does not match body we sent")
        self._validate_successful_get_response(request_type is S3RequestType.PUT_OBJECT)

    def _on_progress_cancel_after_first_chunk(self, progress):
        self.transferred_len += progress
        self.progress_invoked += 1
        self.s3_request.cancel()

    def test_multipart_get_object_cancel(self):
        # a 5 GB file
        request = self._get_object_request("/get_object_test_5120MB.txt")
        s3_client = s3_client_new(False, self.region, 5 * MB)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as file:
            file.close()
            self.s3_request = s3_client.make_request(
                request=request,
                recv_filepath=file.name,
                type=S3RequestType.GET_OBJECT,
                on_headers=self._on_request_headers,
                on_progress=self._on_progress_cancel_after_first_chunk)
            finished_future = self.s3_request.finished_future
            try:
                finished_future.result(self.timeout)
            except Exception as e:
                self.assertEqual(e.name, "AWS_ERROR_S3_CANCELED")

            # Result check
            self.data_len = int(HttpHeaders(self.response_headers).get("Content-Length"))
            self.assertLess(
                self.transferred_len,
                self.data_len,
                "the cancel failed to block all the following body")

            # The on_finish callback may invoke the progress
            self.assertLessEqual(self.progress_invoked, 2)
            shutdown_event = self.s3_request.shutdown_event
            self.s3_request = None
            self.assertTrue(shutdown_event.wait(self.timeout))
            os.remove(file.name)

    def test_get_object_quick_cancel(self):
        # a 5 GB file
        request = self._get_object_request("/get_object_test_5120MB.txt")
        s3_client = s3_client_new(False, self.region, 5 * MB)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as file:
            file.close()
            s3_request = s3_client.make_request(
                request=request,
                recv_filepath=file.name,
                type=S3RequestType.GET_OBJECT,
                on_headers=self._on_request_headers,
                on_progress=self._on_progress)
            s3_request.cancel()
            finished_future = s3_request.finished_future
            try:
                finished_future.result(self.timeout)
            except Exception as e:
                self.assertEqual(e.name, "AWS_ERROR_S3_CANCELED")
            shutdown_event = s3_request.shutdown_event
            s3_request = None
            self.assertTrue(shutdown_event.wait(self.timeout))
            os.remove(file.name)

    def _put_object_cancel_helper(self, cancel_after_read):
        read_futrue = Future()
        put_body_stream = FakeReadStream(read_futrue)
        data_len = 10 * GB  # some fake length
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name)),
                               ("Content-Type", "text/plain"), ("Content-Length", str(data_len))])
        http_request = HttpRequest("PUT", "/cancelled_request", headers, put_body_stream)
        s3_client = s3_client_new(False, self.region, 8 * MB)
        s3_request = s3_client.make_request(
            request=http_request,
            type=S3RequestType.PUT_OBJECT,
            on_headers=self._on_request_headers)

        if cancel_after_read:
            read_futrue.result(self.timeout)
        s3_request.cancel()
        finished_future = s3_request.finished_future
        try:
            finished_future.result(self.timeout)
        except Exception as e:
            self.assertEqual(e.name, "AWS_ERROR_S3_CANCELED")

        shutdown_event = s3_request.shutdown_event
        s3_request = None
        self.assertTrue(shutdown_event.wait(self.timeout))
        # TODO If CLI installed, run the following command to ensure the cancel succeed.
        # aws s3api list-multipart-uploads --bucket aws-crt-canary-bucket --prefix 'cancelled_request'
        # Nothing should printout

    def test_multipart_put_object_cancel(self):
        return self._put_object_cancel_helper(True)

    def test_put_object_quick_cancel(self):
        return self._put_object_cancel_helper(False)

    def test_multipart_upload_with_invalid_request(self):
        request = self._put_object_request(self.default_file_path)
        request.headers.set("Content-MD5", "something")
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT, "AWS_ERROR_S3_INVALID_RESPONSE_STATUS")
        self.put_body_stream.close()

    def test_non_ascii_filepath_upload(self):
        # remove the input file when request done
        with open(self.non_ascii_file_name, 'wb') as file:
            file.write(b"a" * 10 * MB)
        request = self._put_object_request(self.non_ascii_file_name)
        self.put_body_stream.close()
        s3_client = s3_client_new(False, self.region, 5 * MB)
        request_type = S3RequestType.PUT_OBJECT

        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            send_filepath=self.non_ascii_file_name.decode("utf-8"),
            on_headers=self._on_request_headers,
            on_progress=self._on_progress)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)

        # check result
        self.assertEqual(
            self.data_len,
            self.transferred_len,
            "the transferred length reported does not match body we sent")
        self._validate_successful_get_response(request_type is S3RequestType.PUT_OBJECT)
        os.remove(self.non_ascii_file_name)

    def test_non_ascii_filepath_download(self):
        with open(self.non_ascii_file_name, 'wb') as file:
            file.write(b"")
        request = self._get_object_request(self.get_test_object_path)
        request_type = S3RequestType.GET_OBJECT
        s3_client = s3_client_new(False, self.region, 5 * MB)
        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            recv_filepath=self.non_ascii_file_name.decode("utf-8"),
            on_headers=self._on_request_headers,
            on_progress=self._on_progress)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)

        # Result check
        self.data_len = int(HttpHeaders(self.response_headers).get("Content-Length"))
        file_stats = os.stat(self.non_ascii_file_name)
        file_len = file_stats.st_size
        self.assertEqual(
            file_len,
            self.transferred_len,
            "the length of written file does not match the transferred length reported")
        self.assertEqual(
            self.data_len,
            self.transferred_len,
            "the transferred length reported does not match the content-length header")
        self.assertEqual(self.response_status_code, 200, "status code is not 200")
        os.remove(self.non_ascii_file_name)


if __name__ == '__main__':
    unittest.main()
