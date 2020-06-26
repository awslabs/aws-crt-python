"""
AWS client-side authentication: standard credentials providers and signing.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from __future__ import absolute_import
import _awscrt
from awscrt import isinstance_str, NativeResource
import awscrt.exceptions
from awscrt.http import HttpRequest
from awscrt.io import ClientBootstrap
from concurrent.futures import Future
import datetime
from enum import IntEnum
import time

try:
    _utc = datetime.timezone.utc
except AttributeError:
    # Python 2 lacks the datetime.timestamp() method.
    # We can do the timestamp math ourselves, but only if datetime.tzinfo is set.
    # Python 2 also lacks any predefined tzinfo classes (ex: datetime.timezone.utc),
    # so we must define our own.
    class _UTC(datetime.tzinfo):
        ZERO = datetime.timedelta(0)

        def utcoffset(self, dt):
            return _UTC.ZERO

        def tzname(self, dt):
            return "UTC"

        def dst(self, dt):
            return _UTC.ZERO

    _utc = _UTC()


class AwsCredentials(NativeResource):
    """
    AwsCredentials are the public/private data needed to sign an authenticated AWS request.

    AwsCredentials are immutable.

    Args:
        access_key_id (str): Access key ID
        secret_access_key (str): Secret access key
        session_token (Optional[str]): Session token

    Attributes:
        access_key_id (str): Access key ID
        secret_access_key (str): Secret access key
        session_token (Optional[str]): Session token
    """
    __slots__ = ()

    def __init__(self, access_key_id, secret_access_key, session_token=None):
        assert isinstance_str(access_key_id)
        assert isinstance_str(secret_access_key)
        assert isinstance_str(session_token) or session_token is None

        super(AwsCredentials, self).__init__()
        self._binding = _awscrt.credentials_new(access_key_id, secret_access_key, session_token)

    @classmethod
    def _from_binding(cls, binding):
        """Construct from a pre-existing native object"""
        credentials = cls.__new__(cls)  # avoid class's default constructor
        super(cls, credentials).__init__()  # just invoke parent class's __init__()
        credentials._binding = binding
        return credentials

    @property
    def access_key_id(self):
        return _awscrt.credentials_access_key_id(self._binding)

    @property
    def secret_access_key(self):
        return _awscrt.credentials_secret_access_key(self._binding)

    @property
    def session_token(self):
        return _awscrt.credentials_session_token(self._binding)

    def __deepcopy__(self, memo):
        # AwsCredentials is immutable, so just return self.
        return self


class AwsCredentialsProviderBase(NativeResource):
    """
    Base class for providers that source the AwsCredentials needed to sign an authenticated AWS request.

    NOTE: Custom subclasses of AwsCredentialsProviderBase are not yet supported.
    """
    __slots__ = ()

    def __init__(self, binding=None):
        super(AwsCredentialsProviderBase, self).__init__()

        if binding is None:
            # TODO: create binding type that lets native code call into python subclass
            raise NotImplementedError("Custom subclasses of AwsCredentialsProviderBase are not yet supported")

        self._binding = binding

    def get_credentials(self):
        """
        Asynchronously fetch AwsCredentials.

        Returns:
            concurrent.futures.Future: A Future which will contain
            :class:`AwsCredentials` (or an exception) when the operation completes.
            The operation may complete on a different thread.
        """
        raise NotImplementedError()


class AwsCredentialsProvider(AwsCredentialsProviderBase):
    """
    Credentials providers source the AwsCredentials needed to sign an authenticated AWS request.

    Base class: AwsCredentialsProviderBase

    This class provides `new()` functions for several built-in provider types.
    """
    __slots__ = ()

    @classmethod
    def new_default_chain(cls, client_bootstrap):
        """
        Create the default provider chain used by most AWS SDKs.

        Generally:

        1.  Environment
        2.  Profile
        3.  (conditional, off by default) ECS
        4.  (conditional, on by default) EC2 Instance Metadata

        Returns:
            AwsCredentialsProvider:
        """
        assert isinstance(client_bootstrap, ClientBootstrap)

        binding = _awscrt.credentials_provider_new_chain_default(client_bootstrap)
        return cls(binding)

    @classmethod
    def new_static(cls, access_key_id, secret_access_key, session_token=None):
        """
        Create a simple provider that just returns a fixed set of credentials.

        Returns:
            AwsCredentialsProvider:
        """
        assert isinstance_str(access_key_id)
        assert isinstance_str(secret_access_key)
        assert isinstance_str(session_token) or session_token is None

        binding = _awscrt.credentials_provider_new_static(access_key_id, secret_access_key, session_token)
        return cls(binding)

    def get_credentials(self):
        future = Future()

        def _on_complete(error_code, binding):
            try:
                if error_code:
                    future.set_exception(awscrt.exceptions.from_code(error_code))
                else:
                    credentials = AwsCredentials._from_binding(binding)
                    future.set_result(credentials)

            except Exception as e:
                future.set_exception(e)

        try:
            _awscrt.credentials_provider_get_credentials(self._binding, _on_complete)
        except Exception as e:
            future.set_result(e)

        return future


class AwsSigningAlgorithm(IntEnum):
    """AWS signing algorithm enumeration."""

    V4 = 0
    """Use Signature Version 4"""


class AwsSignatureType(IntEnum):
    """Which sort of signature should be computed from the signable."""

    HTTP_REQUEST_HEADERS = 0
    """
    A signature for a full HTTP request should be computed,
    with header updates applied to the signing result.
    """

    HTTP_REQUEST_QUERY_PARAMS = 1
    """
    A signature for a full HTTP request should be computed,
    with query param updates applied to the signing result.
    """


class AwsSignedBodyValueType(IntEnum):
    """Controls what goes in the canonical request's body value."""

    EMPTY = 0
    """Use the SHA-256 of the empty string."""

    PAYLOAD = 1
    """Use the SHA-256 of the actual payload."""

    UNSIGNED_PAYLOAD = 2
    """Use the literal string "UNSIGNED-PAYLOAD"."""


class AwsSignedBodyHeaderType(IntEnum):
    """
    Controls if signing adds a header containing the canonical request's signed body value.

    See :class:`AwsSignedBodyValueType`.
    """

    NONE = 0
    """Do not add a header."""

    X_AMZ_CONTENT_SHA_256 = 1
    """Add the "x-amz-content-sha-256" header with the canonical request's signed body value"""


class AwsSigningConfig(NativeResource):
    """
    Configuration for use in AWS-related signing.

    AwsSigningConfig is immutable.

    It is good practice to use a new config for each signature, or the date might get too old.

    Args:
        algorithm (AwsSigningAlgorithm): Which signing algorithm to use.

        signature_type (AwsSignatureType): Which sort of signature should be
            computed from the signable.

        credentials_provider (AwsCredentialsProviderBase): Credentials provider
            to fetch signing credentials with.

        region (str): The region to sign against.

        service (str): Name of service to sign a request for.

        date (Optional[datetime.datetime]): Date and time to use during the
            signing process. If None is provided then
            `datetime.datetime.now(datetime.timezone.utc)` is used.
            Naive dates (lacking timezone info) are assumed to be in local time.

        should_sign_header (Optional[Callable[[str], bool]]):
            Optional function to control which headers are
            a part of the canonical request.

            Skipping auth-required headers will result in an unusable signature.
            Headers injected by the signing process are not skippable.
            This function does not override the internal check function
            (x-amzn-trace-id, user-agent), but rather supplements it.
            In particular, a header will get signed if and only if it returns
            true to both the internal check (skips x-amzn-trace-id, user-agent)
            and this function (if defined).

        use_double_uri_encode (bool): Whether to double-encode the resource path
            when constructing the canonical request (assuming the path is already
            encoded). Default is True. All services except S3 use double encoding.

        should_normalize_uri_path (bool): Whether the resource paths are
            normalized when building the canonical request.

        signed_body_value_type (AwsSignedBodyValueType): Controls what goes in
            the canonical request's body value. Default is to use the SHA-256
            of the actual payload.

        signed_body_header_type (AwsSignedBodyHeaderType): Controls if signing
            adds a header containing the canonical request's signed body value.
            Default is to not add a header.

        expiration_in_seconds (Optional[int]): If set, and signature_type is
            `HTTP_REQUEST_QUERY_PARAMS`, then signing will add "X-Amz-Expires"
            to the query string, equal to the value specified here.

        omit_session_token (bool): If set True, the "X-Amz-Security-Token"
            query param is omitted from the canonical request.
            The default False should be used for most services.
    """
    __slots__ = ('_priv_should_sign_cb')

    _attributes = (
        'algorithm',
        'signature_type',
        'credentials_provider',
        'region',
        'service',
        'date',
        'should_sign_header',
        'use_double_uri_encode',
        'should_normalize_uri_path',
        'signed_body_value_type',
        'signed_body_header_type',
        'expiration_in_seconds',
        'omit_session_token',
    )

    def __init__(self,
                 algorithm,
                 signature_type,
                 credentials_provider,
                 region,
                 service,
                 date=None,
                 should_sign_header=None,
                 use_double_uri_encode=True,
                 should_normalize_uri_path=True,
                 signed_body_value_type=AwsSignedBodyValueType.PAYLOAD,
                 signed_body_header_type=AwsSignedBodyHeaderType.NONE,
                 expiration_in_seconds=None,
                 omit_session_token=False,
                 ):

        assert isinstance(algorithm, AwsSigningAlgorithm)
        assert isinstance(signature_type, AwsSignatureType)
        assert isinstance(credentials_provider, AwsCredentialsProviderBase)
        assert isinstance_str(region)
        assert isinstance_str(service)
        assert callable(should_sign_header) or should_sign_header is None
        assert isinstance(signed_body_value_type, AwsSignedBodyValueType)
        assert isinstance(signed_body_header_type, AwsSignedBodyHeaderType)
        assert expiration_in_seconds is None or expiration_in_seconds > 0

        super(AwsSigningConfig, self).__init__()

        if date is None:
            date = datetime.datetime.now(_utc)

        try:
            timestamp = date.timestamp()
        except AttributeError:
            # Python 2 doesn't have datetime.timestamp() function.
            # If it did we could just call it from binding code instead of calculating it here.
            if date.tzinfo is None:
                timestamp = time.mktime(date.timetuple())
            else:
                epoch = datetime.datetime(1970, 1, 1, tzinfo=_utc)
                timestamp = (date - epoch).total_seconds()

        self._priv_should_sign_cb = should_sign_header

        if should_sign_header is not None:
            def should_sign_header_wrapper(name):
                return should_sign_header(name=name)
        else:
            should_sign_header_wrapper = None

        if expiration_in_seconds is None:
            # C layer uses 0 to indicate None
            expiration_in_seconds = 0

        self._binding = _awscrt.signing_config_new(
            algorithm,
            signature_type,
            credentials_provider,
            region,
            service,
            date,
            timestamp,
            should_sign_header_wrapper,
            use_double_uri_encode,
            should_normalize_uri_path,
            signed_body_value_type,
            signed_body_header_type,
            expiration_in_seconds,
            omit_session_token)

    def replace(self, **kwargs):
        """
        Return an AwsSigningConfig with the same attributes, except for those
        attributes given new values by whichever keyword arguments are specified.
        """
        args = {x: kwargs.get(x, getattr(self, x)) for x in AwsSigningConfig._attributes}
        return AwsSigningConfig(**args)

    @property
    def algorithm(self):
        """AwsSigningAlgorithm: Which signing algorithm to use"""
        return AwsSigningAlgorithm(_awscrt.signing_config_get_algorithm(self._binding))

    @property
    def signature_type(self):
        """AwsSignatureType: Which sort of signature should be computed from the signable."""
        return AwsSignatureType(_awscrt.signing_config_get_signature_type(self._binding))

    @property
    def credentials_provider(self):
        """AwsCredentialsProviderBase: Credentials provider to fetch signing credentials with"""
        return _awscrt.signing_config_get_credentials_provider(self._binding)

    @property
    def region(self):
        """str: The region to sign against"""
        return _awscrt.signing_config_get_region(self._binding)

    @property
    def service(self):
        """str: Name of service to sign a request for"""
        return _awscrt.signing_config_get_service(self._binding)

    @property
    def date(self):
        """
        datetime.datetime: Date and time to use during the signing process.

        If None is provided, then `datetime.datetime.now(datetime.timezone.utc)`
        at time of object construction is used.

        It is good practice to use a new config for each signature, or the date might get too old.
        """
        return _awscrt.signing_config_get_date(self._binding)

    @property
    def should_sign_header(self):
        """
        Optional[Callable[[str], bool]]: Optional function to control which
        headers are a part of the canonical request.

        Skipping auth-required headers will result in an unusable signature.
        Headers injected by the signing process are not skippable.
        This function does not override the internal check function
        (x-amzn-trace-id, user-agent), but rather supplements it. In particular,
        a header will get signed if and only if it returns true to both
        the internal check (skips x-amzn-trace-id, user-agent) and this function (if defined).
        """
        return self._priv_should_sign_cb

    @property
    def use_double_uri_encode(self):
        """
        bool: Whether to double-encode the resource path when constructing
        the canonical request (assuming the path is already encoded).

        By default, all services except S3 use double encoding.
        """
        return _awscrt.signing_config_get_use_double_uri_encode(self._binding)

    @property
    def should_normalize_uri_path(self):
        """
        bool: Whether the resource paths are normalized when building the
        canonical request.
        """
        return _awscrt.signing_config_get_should_normalize_uri_path(self._binding)

    @property
    def signed_body_value_type(self):
        """
        AwsSignedBodyValueType: Controls what goes in the canonical request's body value.
        """
        return AwsSignedBodyValueType(_awscrt.signing_config_get_signed_body_value_type(self._binding))

    @property
    def signed_body_header_type(self):
        """
        AwsSignedBodyHeaderType: Controls if signing adds a header containing
        the canonical request's signed body value.
        """
        return AwsSignedBodyHeaderType(_awscrt.signing_config_get_signed_body_header_type(self._binding))

    @property
    def expiration_in_seconds(self):
        """
        Optional[int]: If set, and signature_type is `HTTP_REQUEST_QUERY_PARAMS`,
        then signing will add "X-Amz-Expires" to the query string, equal to the
        value specified here. Otherwise, this is None has no effect.
        """
        expiration = _awscrt.signing_config_get_expiration_in_seconds(self._binding)
        # C layer uses 0 to indicate None
        return None if expiration == 0 else expiration

    @property
    def omit_session_token(self):
        """
        bool: Whether the "X-Amz-Security-Token" query param is omitted
        from the canonical request. This should be False for most services.
        """
        return _awscrt.signing_config_get_omit_session_token(self._binding)


def aws_sign_request(http_request, signing_config):
    """
    Perform AWS HTTP request signing.

    The :class:`awscrt.http.HttpRequest` is transformed asynchronously,
    according to the :class:`AwsSigningConfig`.

    When signing:

    1.  It is good practice to use a new config for each signature,
        or the date might get too old.

    2.  Do not add the following headers to requests before signing, they may be added by the signer:
        x-amz-content-sha256,
        X-Amz-Date,
        Authorization

    3.  Do not add the following query params to requests before signing, they may be added by the signer:
        X-Amz-Signature,
        X-Amz-Date,
        X-Amz-Credential,
        X-Amz-Algorithm,
        X-Amz-SignedHeaders

    Args:
        http_request (awscrt.http.HttpRequest): The HTTP request to sign.
        signing_config (AwsSigningConfig): Configuration for signing.

    Returns:
        concurrent.futures.Future: A Future whose result will be the signed
        :class:`awscrt.http.HttpRequest`. The future will contain an exception
        if the signing process fails.
    """

    assert isinstance(http_request, HttpRequest)
    assert isinstance(signing_config, AwsSigningConfig)

    future = Future()

    def _on_complete(error_code):
        try:
            if error_code:
                future.set_exception(awscrt.exceptions.from_code(error_code))
            else:
                future.set_result(http_request)
        except Exception as e:
            future.set_exception(e)

    _awscrt.sign_request_aws(http_request, signing_config, _on_complete)
    return future
