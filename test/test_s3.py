# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import base64
from io import BytesIO
import unittest
import os
import tempfile
import math
import shutil
import time
from test import NativeResourceTest
from concurrent.futures import Future
from multiprocessing import Process

from awscrt.http import HttpHeaders, HttpRequest
from awscrt.s3 import (
    S3ChecksumAlgorithm,
    S3ChecksumConfig,
    S3ChecksumLocation,
    S3Client,
    S3RequestType,
    S3ResponseError,
    CrossProcessLock,
    create_default_s3_signing_config,
    get_optimized_platforms,
)
from awscrt.io import (
    ClientBootstrap,
    ClientTlsContext,
    DefaultHostResolver,
    EventLoopGroup,
    TlsConnectionOptions,
    TlsContextOptions,
)
from awscrt.auth import (
    AwsCredentialsProvider,
    AwsSignatureType,
    AwsSignedBodyHeaderType,
    AwsSignedBodyValue,
    AwsSigningAlgorithm,
    AwsSigningConfig,
)
import zlib

MB = 1024 ** 2
GB = 1024 ** 3

cross_process_lock_name = "instance_lock_test"


def cross_proc_task():
    try:
        lock = CrossProcessLock(cross_process_lock_name)
        lock.acquire()
        lock.release()
        exit(0)
    except RuntimeError as e:
        exit(-1)


class CrossProcessLockTest(NativeResourceTest):
    def setUp(self):
        self.nonce = time.time()
        super().setUp()

    def test_with_statement(self):
        nonce_str = f'lock_a_{self.nonce}'
        with CrossProcessLock(nonce_str) as lock:
            try:
                new_lock = CrossProcessLock(nonce_str)
                new_lock.acquire()
                self.fail("Acquiring a lock by the same nonce should fail when it's already held")
            except RuntimeError as e:
                unique_nonce_str = f'lock_b{self.nonce}'
                new_lock = CrossProcessLock(unique_nonce_str)
                new_lock.acquire()
                new_lock.release()

        lock_after_with_same_nonce = CrossProcessLock(nonce_str)
        lock_after_with_same_nonce.acquire()
        lock_after_with_same_nonce.release()

    def test_cross_proc(self):
        with CrossProcessLock(cross_process_lock_name) as lock:
            process = Process(target=cross_proc_task)
            process.start()
            process.join()
            # aquiring this lock in a sub-process should fail since we
            # already hold the lock in this process.
            self.assertNotEqual(0, process.exitcode)

        # now that we've released the lock above, the same sub-process path
        # should now succeed.
        unlocked_process = Process(target=cross_proc_task)
        unlocked_process.start()
        unlocked_process.join()
        self.assertEqual(0, unlocked_process.exitcode)


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


def s3_client_new(secure, region, part_size=0, is_cancel_test=False, mem_limit=None):

    if is_cancel_test:
        # for cancellation tests, make things slow, so it's less likely that
        # stuff succeeds on other threads before the cancellation is processed.
        num_threads = 1
        throughput_target_gbps = 0.000028  # 28 Kbps beeepdiiingeep beeeeeekskhskshhKKKKchCH
    else:
        # else use defaults
        num_threads = None
        throughput_target_gbps = None

    event_loop_group = EventLoopGroup(num_threads)
    host_resolver = DefaultHostResolver(event_loop_group)
    bootstrap = ClientBootstrap(event_loop_group, host_resolver)
    credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
    signing_config = create_default_s3_signing_config(region=region, credential_provider=credential_provider)
    tls_option = None
    if secure:
        opt = TlsContextOptions()
        ctx = ClientTlsContext(opt)
        tls_option = TlsConnectionOptions(ctx)

    s3_client = S3Client(
        bootstrap=bootstrap,
        region=region,
        signing_config=signing_config,
        tls_connection_options=tls_option,
        part_size=part_size,
        memory_limit=mem_limit,
        throughput_target_gbps=throughput_target_gbps)

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

    def test_get_optimized_platforms(self):
        platform_list = get_optimized_platforms()
        self.assertTrue(len(platform_list) > 0)
        self.assertTrue("p4d.24xlarge" in platform_list)


@unittest.skipUnless(os.environ.get('AWS_TEST_S3'), 'set env var to run test: AWS_TEST_S3')
class S3RequestTest(NativeResourceTest):
    def setUp(self):
        super().setUp()
        # TODO: use env-vars to customize how these tests are run, instead of relying on hard-coded values
        self.get_test_object_path = "/get_object_test_10MB.txt"
        self.put_test_object_path = "/put_object_test_py_10MB.txt"
        self.region = "us-west-2"
        self.bucket_name = "aws-crt-canary-bucket"
        self.timeout = 100  # seconds
        self.num_threads = 0
        self.special_path = "put_object_test_10MB@$%.txt"
        self.non_ascii_file_name = "ÉxÅmple.txt"

        self.response_headers = None
        self.response_status_code = None
        self.received_body_len = 0
        self.transferred_len = 0
        self.data_len = 0
        self.progress_invoked = 0
        self.done_error = None
        self.done_status_code = None
        self.done_error_headers = None
        self.done_error_body = None
        self.done_error_operation_name = None

        self.files = FileCreator()
        self.temp_put_obj_file_path = self.files.create_file_with_size("temp_put_obj_10mb", 10 * MB)

    def tearDown(self):
        self.files.remove_all()
        super().tearDown()

    def _build_endpoint_string(self, region, bucket_name):
        return bucket_name + ".s3." + region + ".amazonaws.com"

    def _get_object_request(self, object_path):
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name))])
        request = HttpRequest("GET", object_path, headers)
        return request

    def _put_object_request(self, input_stream, content_len, path=None, unknown_content_length=False):
        # if send file path is set, the body_stream of http request will be ignored (using file handler from C instead)
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name)),
                               ("Content-Type", "text/plain")])
        if unknown_content_length is False:
            headers.add("Content-Length", str(content_len))
        if path is None:
            path = self.put_test_object_path
        request = HttpRequest("PUT", path, headers, input_stream)
        return request

    def _on_request_headers(self, status_code, headers, **kargs):
        self.response_status_code = status_code
        self.response_headers = headers

    def _on_request_body(self, chunk, offset, **kargs):
        self.received_body_len = self.received_body_len + len(chunk)

    def _on_request_done(self, error, error_headers, error_body, error_operation_name, status_code, **kwargs):
        self.done_error = error
        self.done_error_headers = error_headers
        self.done_error_body = error_body
        self.done_error_operation_name = error_operation_name
        self.done_status_code = status_code

    def _on_progress(self, progress):
        self.transferred_len += progress

    def _validate_successful_response(self, is_put_object):
        self.assertEqual(self.response_status_code, 200, "status code is not 200")
        self.assertEqual(self.done_status_code, self.response_status_code,
                         "status-code from on_done doesn't match code from on_headers")
        self.assertIsNone(self.done_error)
        self.assertIsNone(self.done_error_headers)
        self.assertIsNone(self.done_error_body)
        self.assertIsNone(self.done_error_operation_name)
        headers = HttpHeaders(self.response_headers)
        self.assertIsNone(headers.get("Content-Range"))
        body_length = headers.get("Content-Length")
        if not is_put_object:
            self.assertIsNotNone(body_length, "Content-Length is missing from headers")
        if body_length:
            self.assertEqual(
                int(body_length),
                self.received_body_len,
                "Received body length does not match the Content-Length header")

    def _test_s3_put_get_object(
            self,
            request,
            request_type,
            exception_name=None,
            mem_limit=None,
            **kwargs,
    ):

        s3_client = s3_client_new(False, self.region, 5 * MB, mem_limit=mem_limit)
        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            on_headers=self._on_request_headers,
            on_body=self._on_request_body,
            on_done=self._on_request_done,
            **kwargs)

        finished_future = s3_request.finished_future
        shutdown_event = s3_request.shutdown_event
        s3_request = None
        self.assertTrue(shutdown_event.wait(self.timeout))

        if exception_name is None:
            finished_future.result()
            self._validate_successful_response(request_type is S3RequestType.PUT_OBJECT)
        else:
            e = finished_future.exception()
            self.assertEqual(e.name, exception_name)
            self.assertEqual(e, self.done_error)

    def test_get_object(self):
        request = self._get_object_request(self.get_test_object_path)
        self._test_s3_put_get_object(request, S3RequestType.GET_OBJECT)

    def test_get_object_mem_limit(self):
        request = self._get_object_request(self.get_test_object_path)
        self._test_s3_put_get_object(request, S3RequestType.GET_OBJECT, mem_limit=2 * GB)

    def test_put_object(self):
        put_body_stream = open(self.temp_put_obj_file_path, "rb")
        content_length = os.stat(self.temp_put_obj_file_path).st_size
        request = self._put_object_request(put_body_stream, content_length)
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT)
        put_body_stream.close()

    def test_put_object_mem_limit(self):
        put_body_stream = open(self.temp_put_obj_file_path, "rb")
        content_length = os.stat(self.temp_put_obj_file_path).st_size
        request = self._put_object_request(put_body_stream, content_length)
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT, mem_limit=2 * GB)
        put_body_stream.close()

    def test_put_object_unknown_content_length(self):
        put_body_stream = open(self.temp_put_obj_file_path, "rb")
        content_length = os.stat(self.temp_put_obj_file_path).st_size
        request = self._put_object_request(put_body_stream, content_length, unknown_content_length=True)
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT)
        put_body_stream.close()

    def test_put_object_unknown_content_length_single_part(self):
        data_bytes = "test crt python single part upload".encode(encoding='utf-8')
        put_body_stream = BytesIO(data_bytes)
        request = self._put_object_request(put_body_stream, len(data_bytes), unknown_content_length=True)
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT)
        put_body_stream.close()

    def test_put_object_multiple_times(self):
        s3_client = s3_client_new(False, self.region, 5 * MB)
        finished_futures = []
        for i in range(3):
            tempfile = self.files.create_file_with_size("temp_file_{}".format(str(i)), 10 * MB)
            path = "/put_object_test_py_10MB_{}.txt".format(str(i))
            content_length = os.stat(tempfile).st_size
            request = self._put_object_request(None, content_length, path=path)
            s3_request = s3_client.make_request(
                request=request,
                type=S3RequestType.PUT_OBJECT,
                send_filepath=tempfile,
                on_headers=self._on_request_headers,
                on_body=self._on_request_body,
                on_done=self._on_request_done)
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

    def test_get_object_filepath(self):
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
                on_progress=self._on_progress,
                on_done=self._on_request_done)
            finished_future = s3_request.finished_future

            # Regression test: Let S3Request get GC'd early.
            # The download should continue without problems.
            # We once had a bug where the file would get closed too early:
            # https://github.com/awslabs/aws-crt-python/pull/506
            del s3_request

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

    def test_put_object_filepath(self):
        content_length = os.stat(self.temp_put_obj_file_path).st_size
        request = self._put_object_request(None, content_length)
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT, send_filepath=self.temp_put_obj_file_path)

    def test_put_object_filepath_unknown_content_length(self):
        content_length = os.stat(self.temp_put_obj_file_path).st_size
        request = self._put_object_request(None, content_length, unknown_content_length=True)
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT, send_filepath=self.temp_put_obj_file_path)

    def test_put_object_filepath_move(self):
        # remove the input file when request done
        tempfile = self.files.create_file_with_size("temp_file", 10 * MB)
        content_length = os.stat(tempfile).st_size
        request = self._put_object_request(None, content_length)
        s3_client = s3_client_new(False, self.region, 5 * MB)
        request_type = S3RequestType.PUT_OBJECT
        done_future = Future()

        def on_done_remove_file(**kwargs):
            self._on_request_done(**kwargs)
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
            content_length,
            self.transferred_len,
            "the transferred length reported does not match body we sent")
        self._validate_successful_response(request_type is S3RequestType.PUT_OBJECT)

    def test_put_get_with_checksum(self):
        put_body = b'hello world'
        put_body_stream = BytesIO(put_body)
        content_length = len(put_body)
        path = '/hello-world.txt'

        # calculate expected CRC32 header value:
        # a string containing the url-safe-base64-encoding of a big-endian-32-bit-CRC
        crc32_int = zlib.crc32(put_body)
        crc32_big_endian = crc32_int.to_bytes(4, 'big')
        crc32_base64_bytes = base64.urlsafe_b64encode(crc32_big_endian)
        crc32_base64_str = crc32_base64_bytes.decode()

        # upload, with client adding checksum
        upload_request = self._put_object_request(put_body_stream, content_length, path=path)
        upload_checksum_config = S3ChecksumConfig(
            algorithm=S3ChecksumAlgorithm.CRC32,
            location=S3ChecksumLocation.TRAILER)
        self._test_s3_put_get_object(upload_request, S3RequestType.PUT_OBJECT,
                                     checksum_config=upload_checksum_config)
        self.assertEqual(HttpHeaders(self.response_headers).get('x-amz-checksum-crc32'),
                         crc32_base64_str)

        # download, with client validating checksum
        download_request = self._get_object_request(path)
        download_checksum_config = S3ChecksumConfig(validate_response=True)
        self._test_s3_put_get_object(download_request, S3RequestType.GET_OBJECT,
                                     checksum_config=download_checksum_config)
        self.assertEqual(HttpHeaders(self.response_headers).get('x-amz-checksum-crc32'),
                         crc32_base64_str)

    def _on_progress_cancel_after_first_chunk(self, progress):
        self.transferred_len += progress
        self.progress_invoked += 1
        self.s3_request.cancel()

    def test_multipart_get_object_cancel(self):
        # a 5 GB file
        request = self._get_object_request("/get_object_test_5120MB.txt")
        s3_client = s3_client_new(False, self.region, 5 * MB, is_cancel_test=True)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as file:
            file.close()
            self.s3_request = s3_client.make_request(
                request=request,
                recv_filepath=file.name,
                type=S3RequestType.GET_OBJECT,
                on_headers=self._on_request_headers,
                on_progress=self._on_progress_cancel_after_first_chunk,
                on_done=self._on_request_done)
            finished_future = self.s3_request.finished_future
            e = finished_future.exception(self.timeout)
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
        s3_client = s3_client_new(False, self.region, 5 * MB, is_cancel_test=True)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as file:
            file.close()
            s3_request = s3_client.make_request(
                request=request,
                recv_filepath=file.name,
                type=S3RequestType.GET_OBJECT,
                on_headers=self._on_request_headers,
                on_progress=self._on_progress,
                on_done=self._on_request_done)
            s3_request.cancel()
            finished_future = s3_request.finished_future
            e = finished_future.exception(self.timeout)
            self.assertEqual(e.name, "AWS_ERROR_S3_CANCELED")
            shutdown_event = s3_request.shutdown_event
            s3_request = None
            self.assertTrue(shutdown_event.wait(self.timeout))
            os.remove(file.name)

    def _put_object_cancel_helper(self, cancel_after_read):
        read_future = Future()
        put_body_stream = FakeReadStream(read_future)
        data_len = 10 * GB  # some fake length
        headers = HttpHeaders([("host", self._build_endpoint_string(self.region, self.bucket_name)),
                               ("Content-Type", "text/plain"), ("Content-Length", str(data_len))])
        http_request = HttpRequest("PUT", "/cancelled_request", headers, put_body_stream)
        s3_client = s3_client_new(False, self.region, 8 * MB, is_cancel_test=True)
        s3_request = s3_client.make_request(
            request=http_request,
            type=S3RequestType.PUT_OBJECT,
            on_headers=self._on_request_headers,
            on_done=self._on_request_done)

        if cancel_after_read:
            read_future.result(self.timeout)
        s3_request.cancel()
        finished_future = s3_request.finished_future
        e = finished_future.exception(self.timeout)
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

    def test_singlepart_upload_with_invalid_request(self):
        # send upload with incorrect Content-MD5
        # need to do single-part upload so the Content-MD5 header is sent along as-is.
        content_length = 100
        file_path = self.files.create_file_with_size("temp_file", content_length)
        put_body_stream = open(file_path, "r+b")
        request = self._put_object_request(put_body_stream, content_length)
        request.headers.set("Content-MD5", "something")
        self._test_s3_put_get_object(request, S3RequestType.PUT_OBJECT, "AWS_ERROR_S3_INVALID_RESPONSE_STATUS")

        # check that data from on_done callback came through correctly
        self.assertIsInstance(self.done_error, S3ResponseError)
        self.assertEqual(self.done_status_code, 400)
        self.assertEqual(self.done_error.status_code, 400)
        self.assertIsNotNone(self.done_error_headers)
        self.assertTrue(any(h[0].lower() == 'x-amz-request-id' for h in self.done_error_headers))
        self.assertListEqual(self.done_error_headers, self.done_error.headers)
        self.assertIsNotNone(self.done_error_body)
        self.assertEqual(self.done_error_operation_name, "PutObject")
        self.assertEqual(self.done_error_operation_name, self.done_error.operation_name)
        self.assertTrue(b"InvalidDigest" in self.done_error_body)
        self.assertEqual(self.done_error_body, self.done_error.body)

        put_body_stream.close()

    def test_default_request_failure(self):
        # send invalid DEFAULT S3Request
        # ensure error info (including custom operation_name) comes through correctly
        s3_client = S3Client(region=self.region)

        # send invalid request to S3.
        http_request = HttpRequest(method="GET", path="/obviously-invalid-path-object-does-not-exist")
        http_request.headers.add("host", self._build_endpoint_string(self.region, self.bucket_name))
        http_request.headers.add("content-length", "0")
        s3_request = s3_client.make_request(
            type=S3RequestType.DEFAULT,
            request=http_request,
            operation_name="MyNewOperationName")

        exception = s3_request.finished_future.exception(self.timeout)
        self.assertIsInstance(exception, S3ResponseError)
        self.assertEqual(exception.operation_name, "MyNewOperationName")

    def test_on_headers_callback_failure(self):
        def _explode(**kwargs):
            raise RuntimeError("Error in on_headers callback")

        request = self._get_object_request(self.get_test_object_path)
        s3_client = s3_client_new(False, self.region, 5 * MB)
        s3_request = s3_client.make_request(
            request=request,
            type=S3RequestType.GET_OBJECT,
            on_headers=_explode,
            on_body=self._on_request_body,
        )

        finished_future = s3_request.finished_future
        shutdown_event = s3_request.shutdown_event
        s3_request = None
        self.assertTrue(shutdown_event.wait(self.timeout))

        e = finished_future.exception()
        # check that data from on_done callback came through correctly
        self.assertIsInstance(e, RuntimeError)
        self.assertEqual(str(e), "Error in on_headers callback")

    def test_on_body_callback_failure(self):
        def _explode(**kwargs):
            raise RuntimeError("Error in on_body callback")

        request = self._get_object_request(self.get_test_object_path)
        s3_client = s3_client_new(False, self.region, 5 * MB)
        s3_request = s3_client.make_request(
            request=request,
            type=S3RequestType.GET_OBJECT,
            on_headers=self._on_request_headers,
            on_body=_explode,
        )

        finished_future = s3_request.finished_future
        shutdown_event = s3_request.shutdown_event
        s3_request = None
        self.assertTrue(shutdown_event.wait(self.timeout))

        e = finished_future.exception()
        # check that data from on_done callback came through correctly
        self.assertIsInstance(e, RuntimeError)
        self.assertEqual(str(e), "Error in on_body callback")

    def test_special_filepath_upload(self):
        # remove the input file when request done
        content_length = 10 * MB
        special_path = self.files.create_file_with_size(self.special_path, content_length)

        request = self._put_object_request(None, content_length)
        s3_client = s3_client_new(False, self.region, 5 * MB)
        request_type = S3RequestType.PUT_OBJECT

        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
        # Let signer to normalize uri path for us.
        signing_config = AwsSigningConfig(
            algorithm=AwsSigningAlgorithm.V4,
            signature_type=AwsSignatureType.HTTP_REQUEST_HEADERS,
            service="s3",
            signed_body_header_type=AwsSignedBodyHeaderType.X_AMZ_CONTENT_SHA_256,
            signed_body_value=AwsSignedBodyValue.UNSIGNED_PAYLOAD,
            region=self.region,
            credentials_provider=credential_provider,
            use_double_uri_encode=False,
            should_normalize_uri_path=True,
        )

        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            send_filepath=special_path,
            signing_config=signing_config,
            on_headers=self._on_request_headers,
            on_progress=self._on_progress,
            on_done=self._on_request_done)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)

        # check result
        self.assertEqual(
            content_length,
            self.transferred_len,
            "the transferred length reported does not match body we sent")
        self._validate_successful_response(request_type is S3RequestType.PUT_OBJECT)
        os.remove(special_path)

    def test_non_ascii_filepath_upload(self):
        # remove the input file when request done
        content_length = 10 * MB
        non_ascii_file_path = self.files.create_file_with_size(self.non_ascii_file_name, content_length)
        request = self._put_object_request(None, content_length)
        s3_client = s3_client_new(False, self.region, 5 * MB)
        request_type = S3RequestType.PUT_OBJECT

        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            send_filepath=non_ascii_file_path,
            on_headers=self._on_request_headers,
            on_progress=self._on_progress,
            on_done=self._on_request_done)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)

        # check result
        self.assertEqual(
            content_length,
            self.transferred_len,
            "the transferred length reported does not match body we sent")
        self._validate_successful_response(request_type is S3RequestType.PUT_OBJECT)

    def test_non_ascii_filepath_download(self):
        non_ascii_file_path = self.files.create_file_with_size(self.non_ascii_file_name, 0)
        request = self._get_object_request(self.get_test_object_path)
        request_type = S3RequestType.GET_OBJECT
        s3_client = s3_client_new(False, self.region, 5 * MB)
        s3_request = s3_client.make_request(
            request=request,
            type=request_type,
            recv_filepath=non_ascii_file_path,
            on_headers=self._on_request_headers,
            on_progress=self._on_progress,
            on_done=self._on_request_done)
        finished_future = s3_request.finished_future
        finished_future.result(self.timeout)

        # Result check
        self.data_len = int(HttpHeaders(self.response_headers).get("Content-Length"))
        file_stats = os.stat(non_ascii_file_path)
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


if __name__ == '__main__':
    unittest.main()
