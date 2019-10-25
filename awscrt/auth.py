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
from awscrt.io import ClientBootstrap
from concurrent.futures import Future


class Credentials(object):
    """
    Credentials are the public/private data needed to sign an authenticated AWS request.
    """

    __slots__ = ('access_key_id', 'secret_access_key', 'session_token')

    def __init__(self, access_key_id, secret_access_key, session_token=None):
        assert isinstance_str(access_key_id)
        assert isinstance_str(secret_access_key)
        assert isinstance_str(session_token) or session_token is None

        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.session_token = session_token


class CredentialsProviderBase(NativeResource):
    """
    Base class for providers that source the Credentials needed to sign an authenticated AWS request.

    Custom subclasses are not currently supported.
    """

    def get_credentials(self):
        """
        Asynchronously fetch Credentials.

        Returns a Future which will contain Credentials (or an exception)
        when the call completes. The call may complete on a different thread.
        """
        raise NotImplementedError

    def close(self):
        """
        Signal a provider (and all linked providers) to cancel pending queries and
        stop accepting new ones.  Useful to hasten shutdown time if you know the provider
        is going away.
        """
        raise NotImplementedError


class CredentialsProvider(CredentialsProviderBase):
    """
    Providers source the Credentials needed to sign an authenticated AWS request.

    The `CredentialsProvider` class wraps native implementations supplied by awscrt.
    Instantiate with factory functions such as `new_default_chain()`.
    """

    @classmethod
    def new_default_chain(cls, client_bootstrap):
        """
        Creates the default provider chain used by most AWS SDKs.

        Generally:

        (1) Environment
        (2) Profile
        (3) (conditional, off by default) ECS
        (4) (conditional, on by default) EC2 Instance Metadata
        """
        assert isinstance(client_bootstrap, ClientBootstrap)

        binding = _awscrt.credentials_provider_new_chain_default(client_bootstrap)
        return cls(binding)

    @classmethod
    def new_static(cls, access_key_id, secret_access_key, session_token=None):
        """
        Create a simple provider that just returns a fixed set of credentials
        """
        assert isinstance_str(access_key_id)
        assert isinstance_str(secret_access_key)
        assert isinstance_str(session_token) or session_token is None

        binding = _awscrt.credentials_provider_new_static(access_key_id, secret_access_key, session_token)
        return cls(binding)

    def __init__(self, binding):
        """
        Do not instantiate directly, use CredentialsProvider.new_XYZ() functions.
        """
        assert binding.__class__.__name__ == 'PyCapsule'

        super(CredentialsProvider, self).__init__()
        self._binding = binding

    def get_credentials(self):
        future = Future()

        def _on_complete(error_code, access_key_id, secret_access_key, session_token):
            try:
                if error_code:
                    future.set_exception(Exception(error_code))  # TODO: Actual exceptions for error_codes
                else:
                    credentials = Credentials(access_key_id, secret_access_key, session_token)
                    future.set_result(credentials)

            except Exception as e:
                future.set_exception(e)

        try:
            _awscrt.credentials_provider_get_credentials(self._binding, _on_complete)
        except Exception as e:
            future.set_result(e)

        return future

    def close(self):
        _awscrt.credentials_provider_shutdown(self._binding)
