"""
S3 client
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from concurrent.futures import Future
from awscrt import NativeResource
from awscrt.http import HttpRequest
from awscrt.io import ClientBootstrap, TlsConnectionOptions
from awscrt.auth import AwsCredentialsProvider
import awscrt.exceptions
import threading
from enum import IntEnum


class AwsS3RequestType(IntEnum):
    """The type of the Aws S3 request"""

    DEFAULT = 0
    """
    Default type, which is all the rest type of S3 requests besides of GET_OBJECT/PUT_OBJECT
    """

    GET_OBJECT = 1
    """
    Get Object S3 request
    """

    PUT_OBJECT = 2
    """
    Put Object S3 request
    """


class S3Client(NativeResource):
    """S3 client

    Args:
        bootstrap (ClientBootstrap): Client bootstrap to use when initiating socket connection.

        region (str): Region that the S3 bucket lives in.

        credential_provider (Optional[AwsCredentialsProvider]): Credentials providers source the
            AwsCredentials needed to sign an authenticated AWS request.
            If None is provided, then the default chain credential provider will be used

        tls_connection_options (Optional[TlsConnectionOptions]): Optional TLS
            connection options. If None is provided, then the connection will
            be attempted over plain-text.

        part_size (Optional[int]): Size of parts in Byte the files will be downloaded or uploaded in.
            Note: for PUT_OBJECT request, S3 requires the part size greater than 5MB. (5*1024*1024 by default)

        throughput_target_gbps (Optional[float]): Throughput target in Gbps that we are trying to reach.
            (5 Gbps by default)
    """

    __slots__ = ('shutdown_event')

    def __init__(
            self,
            *,
            bootstrap,
            region,
            credential_provider=None,
            tls_connection_options=None,
            part_size=0,
            throughput_target_gbps=0):
        assert isinstance(bootstrap, ClientBootstrap)
        assert isinstance(region, str)
        assert isinstance(credential_provider, AwsCredentialsProvider) or credential_provider is None
        assert isinstance(tls_connection_options, TlsConnectionOptions) or tls_connection_options is None
        assert isinstance(part_size, int) or part_size is None
        assert isinstance(
            throughput_target_gbps,
            int) or isinstance(
            throughput_target_gbps,
            float) or throughput_target_gbps is None

        super().__init__()

        shutdown_event = threading.Event()

        def on_shutdown():
            shutdown_event.set()

        self.shutdown_event = shutdown_event

        self._binding = _awscrt.s3_client_new(
            bootstrap,
            credential_provider,
            tls_connection_options,
            on_shutdown,
            region,
            part_size,
            throughput_target_gbps)

    def make_request(self, *, request, type, on_headers=None, on_body=None, on_done=None, **kwargs):
        """Create the Request to the the S3 server,
        accelerate the GET_OBJECT/PUT_OBJECT request by spliting it into multiple requests under the hood.

        Args:
            request (HttpRequest): The overall outgoing API request for S3 operation.

            type (AwsS3RequestType): The type of S3 request passed in, GET_OBJECT/PUT_OBJECT can be accelerated

            on_headers: Optional callback invoked as the response received, and even the API request
                has been splitted into multiple parts, this callback will only be invoked once as
                it's just making one API request to S3.
                The function should take the following arguments and return nothing:

                *   `status_code` (int): Response status code.

                *   `headers` (List[Tuple[str, str]]): Response headers as a
                    list of (name,value) pairs.

                *   `**kwargs` (dict): Forward-compatibility kwargs.

            on_body: Optional callback invoked 0+ times as the response body received from S3 server.
                The function should take the following arguments and return nothing:

                *   `chunk` (buffer): Response body data (not necessarily
                    a whole "chunk" of chunked encoding).

                *   `offset` (int): The offset of the chunk started in the whole body.

                *   `**kwargs` (dict): Forward-compatibility kwargs.

            on_done: Optional callback invoked when the meta_request has finished the job.
                The function should take the following arguments and return nothing:

                *   `error_code` (int): The error code from CRT, indicates the job has finished successfully
                    or failed for specific reason

                *   `**kwargs` (dict): Forward-compatibility kwargs.

        Returns:
            S3Request
        """
        return S3Request(
            client=self,
            request=request,
            type=type,
            on_headers=on_headers,
            on_body=on_body,
            on_done=on_done,
            **kwargs)


class S3Request(NativeResource):
    """S3 request

    """
    __slots__ = ('_on_headers_cb', '_on_body_cb', '_on_done_cb', '_finished_future', '_kwargs', 'shutdown_event')

    def __init__(self, *, client, request, type, on_headers=None, on_body=None, on_done=None, **kwargs):
        assert isinstance(client, S3Client)
        assert isinstance(request, HttpRequest)
        assert callable(on_headers) or on_headers is None
        assert callable(on_body) or on_body is None
        assert callable(on_done) or on_done is None

        super().__init__()

        # the native s3-request will keep the request alive until the s3-request finishes
        self._on_headers_cb = on_headers
        self._on_body_cb = on_body
        self._on_done_cb = on_done
        self._kwargs = kwargs

        self._finished_future = Future()

        shutdown_event = threading.Event()

        def on_shutdown():
            shutdown_event.set()

        self.shutdown_event = shutdown_event

        self._binding = _awscrt.s3_client_make_meta_request(
            self, client, request, type, self._on_headers, self._on_body, self._on_finish, on_shutdown)

    def _on_headers(self, status_code, headers):
        if self._on_headers_cb:
            self._on_headers_cb(status_code=status_code, headers=headers, **self._kwargs)

    def _on_body(self, chunk, offset):
        if self._on_body_cb:
            self._on_body_cb(chunk=chunk, offset=offset, kwargs=self._kwargs)

    def _on_finish(self, error_code):
        if error_code:
            self.finished_future.set_exception(awscrt.exceptions.from_code(error_code))
        else:
            self.finished_future.set_result("finish")
        if self._on_done_cb:
            self._on_done_cb(error_code=error_code, kwargs=self._kwargs)

    @property
    def finished_future(self):
        return self._finished_future
