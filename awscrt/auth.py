# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

from __future__ import absolute_import
import _awscrt
from awscrt import isinstance_str, NativeResource
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
    """
    __slots__ = ()

    def __init__(self, access_key_id, secret_access_key, session_token=None):
        assert isinstance_str(access_key_id)
        assert isinstance_str(secret_access_key)
        assert isinstance_str(session_token) or session_token is None

        super(AwsCredentials, self).__init__()
        self._binding = _awscrt.credentials_new(access_key_id, secret_access_key, session_token)

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
    """
    __slots__ = ()

    def get_credentials(self):
        """
        Asynchronously fetch AwsCredentials.

        Returns a Future which will contain AwsCredentials (or an exception)
        when the call completes. The call may complete on a different thread.
        """
        future = Future()

        def _on_complete(error_code, access_key_id, secret_access_key, session_token):
            try:
                if error_code:
                    future.set_exception(Exception(error_code))  # TODO: Actual exceptions for error_codes
                else:
                    credentials = AwsCredentials(access_key_id, secret_access_key, session_token)
                    future.set_result(credentials)

            except Exception as e:
                future.set_exception(e)

        try:
            _awscrt.credentials_provider_get_credentials(self._binding, _on_complete)
        except Exception as e:
            future.set_result(e)

        return future

    def close(self):
        """
        Signal a provider (and all linked providers) to cancel pending queries and
        stop accepting new ones.  Useful to hasten shutdown time if you know the provider
        is going away.
        """
        _awscrt.credentials_provider_shutdown(self._binding)


class DefaultAwsCredentialsProviderChain(AwsCredentialsProviderBase):
    """
    Providers source the AwsCredentials needed to sign an authenticated AWS request.
    This is the default provider chain used by most AWS SDKs.

    Generally:

    (1) Environment
    (2) Profile
    (3) (conditional, off by default) ECS
    (4) (conditional, on by default) EC2 Instance Metadata
    """
    __slots__ = ()

    def __init__(self, client_bootstrap):
        assert isinstance(client_bootstrap, ClientBootstrap)

        super(DefaultAwsCredentialsProviderChain, self).__init__()
        self._binding = _awscrt.credentials_provider_new_chain_default(client_bootstrap)


class StaticAwsCredentialsProvider(AwsCredentialsProviderBase):
    """
    Providers source the AwsCredentials needed to sign an authenticated AWS request.
    This is a simple provider that just returns a fixed set of credentials
    """
    __slots__ = ()

    def __init__(self, access_key_id, secret_access_key, session_token=None):
        assert isinstance_str(access_key_id)
        assert isinstance_str(secret_access_key)
        assert isinstance_str(session_token) or session_token is None

        super(StaticAwsCredentialsProvider, self).__init__()
        self._binding = _awscrt.credentials_provider_new_static(access_key_id, secret_access_key, session_token)


class AwsSigningAlgorithm(IntEnum):
    """
    Which signing algorithm to use.

    Sigv4Header: Use Signature Version 4 to sign headers.
    Sigv4QueryParam: Use Signature Version 4 to sign query parameters.
    """
    Sigv4Header = 0
    Sigv4QueryParam = 1


class AwsSigningConfig(NativeResource):
    """
    Configuration for use in AWS-related signing.
    AwsSigningConfig is immutable.
    It is good practice to use a new config for each signature, or the date might get too old.
    """
    __slots__ = ()

    _attributes = ('algorithm', 'credentials_provider', 'region', 'service', 'date', 'should_sign_param',
                   'use_double_uri_encode', 'should_normalize_uri_path', 'sign_body')

    def __init__(self,
                 algorithm,  # type: AwsSigningAlgorithm
                 credentials_provider,  # type: AwsCredentialsProviderBase
                 region,  # type: str
                 service,  # type: str
                 date=datetime.datetime.now(_utc),  # type: datetime.datetime
                 should_sign_param=None,  # type: Optional[Callable[[str], bool]]
                 use_double_uri_encode=False,  # type: bool
                 should_normalize_uri_path=True,  # type: bool
                 sign_body=True  # type: bool
                 ):
        # type: (...) -> None

        assert isinstance(algorithm, AwsSigningAlgorithm)
        assert isinstance(credentials_provider, AwsCredentialsProviderBase)
        assert isinstance_str(region)
        assert isinstance_str(service)
        assert isinstance(date, datetime.datetime)
        assert callable(should_sign_param) or should_sign_param is None

        super(AwsSigningConfig, self).__init__()

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

        self._binding = _awscrt.signing_config_new(
            algorithm,
            credentials_provider,
            region,
            service,
            date,
            timestamp,
            should_sign_param,
            use_double_uri_encode,
            should_normalize_uri_path,
            sign_body)

    def replace(self, **kwargs):
        """
        Return an AwsSigningConfig with the same attributes, except for those
        attributes given new values by whichever keyword arguments are specified.
        """
        args = {x: kwargs.get(x, getattr(self, x)) for x in AwsSigningConfig._attributes}
        return AwsSigningConfig(**args)

    @property
    def algorithm(self):
        """Which AwsSigningAlgorithm to invoke"""
        return AwsSigningAlgorithm(_awscrt.signing_config_get_algorithm(self._binding))

    @property
    def credentials_provider(self):
        """AwsCredentialsProvider to fetch signing credentials with"""
        return _awscrt.signing_config_get_credentials_provider(self._binding)

    @property
    def region(self):
        """The region to sign against"""
        return _awscrt.signing_config_get_region(self._binding)

    @property
    def service(self):
        """Name of service to sign a request for"""
        return _awscrt.signing_config_get_service(self._binding)

    @property
    def date(self):
        """datetime.datetime to use during the signing process"""
        return _awscrt.signing_config_get_date(self._binding)

    @property
    def should_sign_param(self):
        """
        Optional function to control which parameters (header or query) are a part of the canonical request.
        Function signature is: (name) -> bool
        Skipping auth-required params will result in an unusable signature.
        Headers injected by the signing process are not skippable.
        This function does not override the internal check function (x-amzn-trace-id, user-agent), but rather
        supplements it.  In particular, a header will get signed if and only if it returns true to both
        the internal check (skips x-amzn-trace-id, user-agent) and this function (if defined).
        """
        return _awscrt.signing_config_get_should_sign_param(self._binding)

    @property
    def use_double_uri_encode(self):
        """
        We assume the uri will be encoded once in preparation for transmission.  Certain services
        do not decode before checking signature, requiring us to actually double-encode the uri in the canonical request
        in order to pass a signature check.
        """
        return _awscrt.signing_config_get_use_double_uri_encode(self._binding)

    @property
    def should_normalize_uri_path(self):
        """Controls whether or not the uri paths should be normalized when building the canonical request"""
        return _awscrt.signing_config_get_should_normalize_uri_path(self._binding)

    @property
    def sign_body(self):
        """
        If true adds the x-amz-content-sha256 header (with appropriate value) to the canonical request,
        otherwise does nothing
        """
        return _awscrt.signing_config_get_sign_body(self._binding)


class AwsSigner(NativeResource):
    """
    A signer that performs AWS http request signing.

    When using this signer to sign AWS http requests:

      (1) Do not add the following headers to requests before signing, they may be added by the signer:
         x-amz-content-sha256,
         X-Amz-Date,
         Authorization

      (2) Do not add the following query params to requests before signing, they may be added by the signer:
         X-Amz-Signature,
         X-Amz-Date,
         X-Amz-Credential,
         X-Amz-Algorithm,
         X-Amz-SignedHeaders
    """

    def __init__(self):
        super(AwsSigner, self).__init__()
        self._binding = _awscrt.signer_new_aws()

    def sign(self, http_request, signing_config):
        """
        Asynchronously transform the HttpRequest according to the signing algorithm.
        Returns a Future whose result will be the signed HttpRequest.

        It is good practice to use a new config for each signature, or the date might get too old.
        """
        assert isinstance(http_request, HttpRequest)
        assert isinstance(signing_config, AwsSigningConfig)

        future = Future()

        def _on_complete(error_code):
            try:
                if error_code:
                    future.set_exception(Exception(error_code))  # TODO: Actual exceptions for error_codes
                else:
                    future.set_result(http_request)
            except Exception as e:
                future.set_exception(e)

        _awscrt.signer_sign_request(self, http_request, signing_config, _on_complete)
        return future
