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
from awscrt.auth import AwsCredentialsProvider, AwsSignatureType, AwsSignedBodyHeaderType, AwsSignedBodyValue, \
    AwsSigningAlgorithm, AwsSigningConfig
import awscrt.exceptions
from dataclasses import dataclass
import threading
from typing import Optional
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


class S3ChecksumAlgorithm(IntEnum):
    """
    Checksum algorithm used to verify object integrity.
    https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html
    """

    CRC32C = 1
    """CRC32C"""

    CRC32 = 2
    """CRC32"""

    SHA1 = 3
    """SHA-1"""

    SHA256 = 4
    """SHA-256"""


class S3ChecksumLocation(IntEnum):
    """Where to put the checksum."""

    HEADER = 1
    """
    Add checksum as a request header field.
    The checksum is calculated before any part of the request is sent to the server.
    """

    TRAILER = 2
    """
    Add checksum as a request trailer field.
    The checksum is calculated as the body is streamed to the server, then
    added as a trailer field. This may be more efficient than HEADER, but
    can only be used with "streaming" requests that support it.
    """


@dataclass
class S3ChecksumConfig:
    """Configures how the S3Client calculates and verifies checksums."""

    algorithm: Optional[S3ChecksumAlgorithm] = None
    """
    If set, the S3Client will calculate a checksum using this algorithm
    and add it to the request. If you set this, you must also set `location`.
    """

    location: Optional[S3ChecksumLocation] = None
    """Where to put the request checksum."""

    validate_response: bool = False
    """Whether to retrieve and validate response checksums."""


class S3Client(NativeResource):
    """S3 client

    Keyword Args:
        bootstrap (Optional [ClientBootstrap]): Client bootstrap to use when initiating socket connection.
            If None is provided, the default singleton is used.

        region (str): Region that the S3 bucket lives in.

        tls_mode (Optional[S3RequestTlsMode]):  How TLS should be used while performing the request

            If this is :attr:`S3RequestTlsMode.ENABLED`:
                If `tls_connection_options` is set, then those TLS options will be used
                If `tls_connection_options` is unset, then default TLS options will be used

            If this is :attr:`S3RequestTlsMode.DISABLED`:
                No TLS options will be used, regardless of `tls_connection_options` value.

        signing_config (Optional[AwsSigningConfig]):
             Configuration for signing of the client. Use :func:`create_default_s3_signing_config()` to create the default config.
             If None is provided, the request will not be signed.

        credential_provider (Optional[AwsCredentialsProvider]): Deprecated, prefer `signing_config` instead.
            Credentials providers source the :class:`~awscrt.auth.AwsCredentials` needed to sign an authenticated AWS request.
            If None is provided, the request will not be signed.

        tls_connection_options (Optional[TlsConnectionOptions]): Optional TLS Options to be used
            for each connection, unless `tls_mode` is :attr:`S3RequestTlsMode.DISABLED`

        part_size (Optional[int]): Size, in bytes, of parts that files will be downloaded or uploaded in.
            Note: for :attr:`S3RequestType.PUT_OBJECT` request, S3 requires the part size greater than 5 MiB.
            (8*1024*1024 by default)

        multipart_upload_threshold (Optional[int]): The size threshold in bytes, for when to use multipart uploads.
            Uploads over this size will use the multipart upload strategy.
            Uploads this size or less will use a single request.
            If not set, `part_size` is used as the threshold.

        throughput_target_gbps (Optional[float]): Throughput target in
            Gigabits per second (Gbps) that we are trying to reach.
            (10.0 Gbps by default)
    """

    __slots__ = ('shutdown_event', '_region')

    def __init__(
            self,
            *,
            bootstrap,
            region,
            tls_mode=None,
            signing_config=None,
            credential_provider=None,
            tls_connection_options=None,
            part_size=None,
            multipart_upload_threshold=None,
            throughput_target_gbps=None):
        assert isinstance(bootstrap, ClientBootstrap) or bootstrap is None
        assert isinstance(region, str)
        assert isinstance(signing_config, AwsSigningConfig) or signing_config is None
        assert isinstance(credential_provider, AwsCredentialsProvider) or credential_provider is None
        assert isinstance(tls_connection_options, TlsConnectionOptions) or tls_connection_options is None
        assert isinstance(part_size, int) or part_size is None
        assert isinstance(
            throughput_target_gbps,
            int) or isinstance(
            throughput_target_gbps,
            float) or throughput_target_gbps is None

        if credential_provider and signing_config:
            raise ValueError("'credential_provider' has been deprecated in favor of 'signing_config'.  "
                             "Both parameters may not be set.")

        super().__init__()

        shutdown_event = threading.Event()

        def on_shutdown():
            shutdown_event.set()

        self._region = region
        self.shutdown_event = shutdown_event

        if not bootstrap:
            bootstrap = ClientBootstrap.get_or_create_static_default()

        s3_client_core = _S3ClientCore(bootstrap, credential_provider, signing_config, tls_connection_options)

        # C layer uses 0 to indicate defaults
        if tls_mode is None:
            tls_mode = 0
        if part_size is None:
            part_size = 0
        if multipart_upload_threshold is None:
            multipart_upload_threshold = 0
        if throughput_target_gbps is None:
            throughput_target_gbps = 0

        self._binding = _awscrt.s3_client_new(
            bootstrap,
            signing_config,
            credential_provider,
            tls_connection_options,
            on_shutdown,
            region,
            tls_mode,
            part_size,
            multipart_upload_threshold,
            throughput_target_gbps,
            s3_client_core)

    def make_request(
            self,
            *,
            type,
            request,
            recv_filepath=None,
            send_filepath=None,
            signing_config=None,
            credential_provider=None,
            checksum_config=None,
            on_headers=None,
            on_body=None,
            on_done=None,
            on_progress=None):
        """Create the Request to the the S3 server,
        :attr:`~S3RequestType.GET_OBJECT`/:attr:`~S3RequestType.PUT_OBJECT` requests are split it into multi-part
        requests under the hood for acceleration.

        Keyword Args:
            type (S3RequestType): The type of S3 request passed in,
                :attr:`~S3RequestType.GET_OBJECT`/:attr:`~S3RequestType.PUT_OBJECT` can be accelerated

            request (HttpRequest): The overall outgoing API request for S3 operation.
                If the request body is a file, set send_filepath for better performance.

            recv_filepath (Optional[str]): Optional file path. If set, the
                response body is written directly to a file and the
                `on_body` callback is not invoked. This should give better
                performance than writing to file from the `on_body` callback.

            send_filepath (Optional[str]): Optional file path. If set, the
                request body is read directly from a file and the
                request's `body_stream` is ignored. This should give better
                performance than reading a file from a stream.

            signing_config (Optional[AwsSigningConfig]):
                Configuration for signing of the request to override the configuration from client. Use :func:`create_default_s3_signing_config()` to create the default config.
                If None is provided, the client configuration will be used.

            credential_provider (Optional[AwsCredentialsProvider]):  Deprecated, prefer `signing_config` instead.
                Credentials providers source the :class:`~awscrt.auth.AwsCredentials` needed to sign an authenticated AWS request, for this request only.
                If None is provided, the client configuration will be used.

            checksum_config (Optional[S3ChecksumConfig]): Optional checksum settings.

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

                    *   `error_body` (Optional[bytes]): If request failed because server
                        side sent an unsuccessful response, the body of the response is
                        provided here. Else None will be returned.

                    *   `status_code` (Optional[int]): HTTP response status code (if available).
                        If request failed because server side sent an unsuccessful response,
                        this is its status code. If the operation was successful,
                        this is the final response's status code. If the operation
                        failed for another reason, None is returned.

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
            type=type,
            request=request,
            recv_filepath=recv_filepath,
            send_filepath=send_filepath,
            signing_config=signing_config,
            credential_provider=credential_provider,
            checksum_config=checksum_config,
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
            type,
            request,
            recv_filepath=None,
            send_filepath=None,
            signing_config=None,
            credential_provider=None,
            checksum_config=None,
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

        checksum_algorithm = 0  # 0 means NONE in C
        checksum_location = 0  # 0 means NONE in C
        validate_response_checksum = False
        if checksum_config is not None:
            if checksum_config.algorithm is not None:
                checksum_algorithm = checksum_config.algorithm.value
            if checksum_config.location is not None:
                checksum_location = checksum_config.location.value
            validate_response_checksum = checksum_config.validate_response

        s3_request_core = _S3RequestCore(
            request,
            self._finished_future,
            self.shutdown_event,
            signing_config,
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
            signing_config,
            credential_provider,
            recv_filepath,
            send_filepath,
            region,
            checksum_algorithm,
            checksum_location,
            validate_response_checksum,
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
                 signing_config=None,
                 tls_connection_options=None):
        self._bootstrap = bootstrap
        self._credential_provider = credential_provider
        self._signing_config = signing_config
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
            signing_config=None,
            credential_provider=None,
            on_headers=None,
            on_body=None,
            on_done=None,
            on_progress=None):

        self._request = request
        self._signing_config = signing_config
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

    def _on_finish(self, error_code, status_code, error_headers, error_body):
        # If C layer gives status_code 0, that means "unknown"
        if status_code == 0:
            status_code = None

        error = None
        if error_code:
            error = awscrt.exceptions.from_code(error_code)
            if error_body:
                # TODO The error body is XML, will need to parse it to something prettier.
                try:
                    extra_message = ". Body from error request is: " + str(error_body)
                    error.message = error.message + extra_message
                except BaseException:
                    pass
            self._finished_future.set_exception(error)
        else:
            self._finished_future.set_result(None)
        if self._on_done_cb:
            self._on_done_cb(error=error, error_headers=error_headers, error_body=error_body, status_code=status_code)

    def _on_progress(self, progress):
        if self._on_progress_cb:
            self._on_progress_cb(progress)


def create_default_s3_signing_config(*, region: str, credential_provider: AwsCredentialsProvider, **kwargs):
    """Create a default `AwsSigningConfig` for S3 service.

        Attributes:
            region (str): The region to sign against.

            credential_provider (AwsCredentialsProvider): Credentials provider
                to fetch signing credentials with.

            `**kwargs`: Forward compatibility kwargs.

        Returns:
            AwsSigningConfig
    """
    return AwsSigningConfig(
        algorithm=AwsSigningAlgorithm.V4,
        signature_type=AwsSignatureType.HTTP_REQUEST_HEADERS,
        service="s3",
        signed_body_header_type=AwsSignedBodyHeaderType.X_AMZ_CONTENT_SHA_256,
        signed_body_value=AwsSignedBodyValue.UNSIGNED_PAYLOAD,
        region=region,
        credentials_provider=credential_provider,
        use_double_uri_encode=False,
        should_normalize_uri_path=False,
    )


def get_ec2_instance_type():
    """
        First this function will check it's running on EC2 via. attempting to read DMI info to avoid making IMDS calls.

        If the function detects it's on EC2, and it was able to detect the instance type without a call to IMDS
        it will return it.

        Finally, it will call IMDS and return the instance type from there.
        Note that in the case of the IMDS call, a new client stack is spun up using 1 background thread. The call is made
        synchronously with a 1 second timeout: It's not cheap. To make this easier, the underlying result is cached
        internally and will be freed when this module is unloaded is called.

        Returns:
           A string indicating the instance type or None if it could not be determined.
    """
    return _awscrt.s3_get_ec2_instance_type()


def is_optimized_for_system():
    """
        Returns:
            true if the current build of this module has an optimized configuration
            for the current system.
    """
    return _awscrt.s3_is_crt_s3_optimized_for_system()
