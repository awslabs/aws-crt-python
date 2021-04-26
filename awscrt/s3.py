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


class S3RequestType(IntEnum):
    """The type of the AWS S3 request"""

    DEFAULT = 0
    """
    Default type, for all S3 request types other than
    :attr:`~S3RequestType.GET_OBJECT`/:attr:`~S3RequestType.PUT_OBJECT`.
    """

    GET_OBJECT = 1
    """
    Get Object S3 request
    """

    PUT_OBJECT = 2
    """
    Put Object S3 request
    """


class S3RequestTlsMode(IntEnum):
    """TLS mode for S3 request"""

    ENABLED = 0
    """
    Enable TLS for S3 request.
    """

    DISABLED = 1
    """
    Disable TLS for S3 request.
    """


class S3Client(NativeResource):
    """S3 client

    Keyword Args:
        bootstrap (ClientBootstrap): Client bootstrap to use when initiating socket connection.

        region (str): Region that the S3 bucket lives in.

        tls_mode (Optional[S3RequestTlsMode]):  How TLS should be used while performing the request

            If this is :attr:`S3RequestTlsMode.ENABLED`:
                If `tls_connection_options` is set, then those TLS options will be used
                If `tls_connection_options` is unset, then default TLS options will be used

            If this is :attr:`S3RequestTlsMode.DISABLED`:
                No TLS options will be used, regardless of `tls_connection_options` value.

        credential_provider (Optional[AwsCredentialsProvider]): Credentials providers source the
            :class:`~awscrt.auth.AwsCredentials` needed to sign an authenticated AWS request.
            If None is provided, the request will not be signed.

        tls_connection_options (Optional[TlsConnectionOptions]): Optional TLS Options to be used
            for each connection, unless `tls_mode` is :attr:`S3RequestTlsMode.DISABLED`

        part_size (Optional[int]): Size, in bytes, of parts that files will be downloaded or uploaded in.
            Note: for :attr:`S3RequestType.PUT_OBJECT` request, S3 requires the part size greater than 5MB.
            (5*1024*1024 by default)

        throughput_target_gbps (Optional[float]): Throughput target in Gbps that we are trying to reach.
            (5 Gbps by default)
    """

    __slots__ = ('shutdown_event', '_region')

    def __init__(
            self,
            *,
            bootstrap,
            region,
            tls_mode=None,
            credential_provider=None,
            tls_connection_options=None,
            part_size=None,
            throughput_target_gbps=None):
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
        self._region = region
        self.shutdown_event = shutdown_event
        s3_client_core = _S3ClientCore(bootstrap, credential_provider, tls_connection_options)

        # C layer uses 0 to indicate defaults
        if tls_mode is None:
            tls_mode = 0
        if part_size is None:
            part_size = 0
        if throughput_target_gbps is None:
            throughput_target_gbps = 0

        self._binding = _awscrt.s3_client_new(
            bootstrap,
            credential_provider,
            tls_connection_options,
            on_shutdown,
            region,
            tls_mode,
            part_size,
            throughput_target_gbps,
            s3_client_core)

    def make_request(
            self,
            *,
            request,
            type,
            credential_provider=None,
            recv_filepath=None,
            send_filepath=None,
            on_headers=None,
            on_body=None,
            on_done=None,
            on_progress=None):
        """Create the Request to the the S3 server,
        :attr:`~S3RequestType.GET_OBJECT`/:attr:`~S3RequestType.PUT_OBJECT` requests are split it into multi-part
        requests under the hood for acceleration.

        Keyword Args:
            request (HttpRequest): The overall outgoing API request for S3 operation.
                If the request body is a file, set send_filepath for better performance.

            type (S3RequestType): The type of S3 request passed in,
                :attr:`~S3RequestType.GET_OBJECT`/:attr:`~S3RequestType.PUT_OBJECT` can be accelerated

            credential_provider (Optional[AwsCredentialsProvider]): Credentials providers source the
                :class:`~awscrt.auth.AwsCredentials` needed to sign an authenticated AWS request, for this request only.
                If None is provided, the credential provider in the client will be used.

            recv_filepath (Optional[str]): Optional file path. If set, the
                response body is written directly to a file and the
                `on_body` callback is not invoked. This should give better
                performance than writing to file from the `on_body` callback.

            send_filepath (Optional[str]): Optional file path. If set, the
                request body is read directly from a file and the
                request's `body_stream` is ignored. This should give better
                performance than reading a file from a stream.

            on_headers: Optional callback invoked as the response received, and even the API request
                has been split into multiple parts, this callback will only be invoked once as
                it's just making one API request to S3.
                The function should take the following arguments and return nothing:

                    *   `status_code` (int): Response status code.

                    *   `headers` (List[Tuple[str, str]]): Response headers as a
                        list of (name,value) pairs.

                    *   `**kwargs` (dict): Forward-compatibility kwargs.

            on_body: Optional callback invoked 0+ times as the response body received from S3 server.
                If simply writing to a file, use `recv_filepath` instead of `on_body` for better performance.
                The function should take the following arguments and return nothing:

                    *   `chunk` (buffer): Response body data (not necessarily
                        a whole "chunk" of chunked encoding).

                    *   `offset` (int): The offset of the chunk started in the whole body.

                    *   `**kwargs` (dict): Forward-compatibility kwargs.

            on_done: Optional callback invoked when the request has finished the job.
                The function should take the following arguments and return nothing:

                    *   `error` (Optional[Exception]): None if the request was
                        successfully sent and valid response received, or an Exception
                        if it failed.

                    *   `error_headers` (Optional[List[Tuple[str, str]]]): If request
                        failed because server side sent an unsuccessful response, the headers
                        of the response is provided here. Else None will be returned.

                    *   `error_body` (Optional[Bytes]): If request failed because server
                        side sent an unsuccessful response, the body of the response is
                        provided here. Else None will be returned.

                    *   `**kwargs` (dict): Forward-compatibility kwargs.

            on_progress: Optional callback invoked when part of the transfer is done to report the progress.
                The function should take the following arguments and return nothing:

                    *   `progress` (int): Number of bytes of data that just get transferred

                    *   `**kwargs` (dict): Forward-compatibility kwargs.

        Returns:
            S3Request
        """
        return S3Request(
            client=self,
            request=request,
            type=type,
            credential_provider=credential_provider,
            recv_filepath=recv_filepath,
            send_filepath=send_filepath,
            on_headers=on_headers,
            on_body=on_body,
            on_done=on_done,
            on_progress=on_progress,
            region=self._region)


class S3Request(NativeResource):
    """S3 request
    Create a new S3Request with :meth:`S3Client.make_request()`

    Attributes:
        finished_future (concurrent.futures.Future): Future that will
            resolve when the s3 request has finished successfully.
            If the error happens, the Future will contain an exception
            indicating why it failed. Note: Future will set before on_done invoked

        shutdown_event (threading.Event): Signals when underlying threads and
            structures have all finished shutting down. Shutdown begins when the
            S3Request object is destroyed.
    """
    __slots__ = ('_finished_future', 'shutdown_event')

    def __init__(
            self,
            *,
            client,
            request,
            type,
            credential_provider=None,
            recv_filepath=None,
            send_filepath=None,
            on_headers=None,
            on_body=None,
            on_done=None,
            on_progress=None,
            region=None):
        assert isinstance(client, S3Client)
        assert isinstance(request, HttpRequest)
        assert callable(on_headers) or on_headers is None
        assert callable(on_body) or on_body is None
        assert callable(on_done) or on_done is None

        super().__init__()

        self._finished_future = Future()
        self.shutdown_event = threading.Event()

        s3_request_core = _S3RequestCore(
            request,
            self._finished_future,
            self.shutdown_event,
            credential_provider,
            on_headers,
            on_body,
            on_done,
            on_progress)

        self._binding = _awscrt.s3_client_make_meta_request(
            self,
            client,
            request,
            type,
            credential_provider,
            recv_filepath,
            send_filepath,
            region,
            s3_request_core)

    @property
    def finished_future(self):
        return self._finished_future

    def cancel(self):
        _awscrt.s3_meta_request_cancel(self)


class _S3ClientCore:
    '''
    Private class to keep all the related Python object alive until C land clean up for S3Client
    '''

    def __init__(self, bootstrap,
                 credential_provider=None,
                 tls_connection_options=None):
        self._bootstrap = bootstrap
        self._credential_provider = credential_provider
        self._tls_connection_options = tls_connection_options


class _S3RequestCore:
    '''
    Private class to keep all the related Python object alive until C land clean up for S3Request
    '''

    def __init__(
            self,
            request,
            finish_future,
            shutdown_event,
            credential_provider=None,
            on_headers=None,
            on_body=None,
            on_done=None,
            on_progress=None):

        self._request = request
        self._credential_provider = credential_provider

        self._on_headers_cb = on_headers
        self._on_body_cb = on_body
        self._on_done_cb = on_done
        self._on_progress_cb = on_progress

        self._finished_future = finish_future
        self._shutdown_event = shutdown_event

    def _on_headers(self, status_code, headers):
        if self._on_headers_cb:
            self._on_headers_cb(status_code=status_code, headers=headers)

    def _on_body(self, chunk, offset):
        if self._on_body_cb:
            self._on_body_cb(chunk=chunk, offset=offset)

    def _on_shutdown(self):
        self._shutdown_event.set()

    def _on_finish(self, error_code, error_headers, error_body):
        error = None
        if error_code:
            error = awscrt.exceptions.from_code(error_code)
            if error_body:
                # TODO The error body is XML, will need to parse it to something prettier.
                extra_message = ". Body from error request is: " + str(error_body)
                error.message = error.message + extra_message
            self._finished_future.set_exception(error)
        else:
            self._finished_future.set_result(None)
        if self._on_done_cb:
            self._on_done_cb(error=error, error_headers=error_headers, error_body=error_body)

    def _on_progress(self, progress):
        if self._on_progress_cb:
            self._on_progress_cb(progress)
