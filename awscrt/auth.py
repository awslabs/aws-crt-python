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
    """

    def get_credentials(self):
        """
        Asynchronously fetch Credentials.

        Returns a Future which will contain Credentials (or an exception)
        when the call completes. The call may complete on a different thread.
        """
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
        """
        Signal a provider (and all linked providers) to cancel pending queries and
        stop accepting new ones.  Useful to hasten shutdown time if you know the provider
        is going away.
        """
        _awscrt.credentials_provider_shutdown(self._binding)


class DefaultCredentialsProviderChain(CredentialsProviderBase):
    """
    Providers source the Credentials needed to sign an authenticated AWS request.
    This is the default provider chain used by most AWS SDKs.

    Generally:

    (1) Environment
    (2) Profile
    (3) (conditional, off by default) ECS
    (4) (conditional, on by default) EC2 Instance Metadata
    """

    def __init__(self, client_bootstrap):
        assert isinstance(client_bootstrap, ClientBootstrap)

        super(DefaultCredentialsProviderChain, self).__init__()
        self._binding = _awscrt.credentials_provider_new_chain_default(client_bootstrap)


class StaticCredentialsProvider(CredentialsProviderBase):
    """
    Providers source the Credentials needed to sign an authenticated AWS request.
    This is a simple provider that just returns a fixed set of credentials
    """

    def __init__(self, access_key_id, secret_access_key, session_token=None):
        assert isinstance_str(access_key_id)
        assert isinstance_str(secret_access_key)
        assert isinstance_str(session_token) or session_token is None

        super(StaticCredentialsProvider, self).__init__()
        self._binding = _awscrt.credentials_provider_new_static(access_key_id, secret_access_key, session_token)
