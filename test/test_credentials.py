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
from awscrt.auth import CredentialsProvider
from awscrt.io import ClientBootstrap, EventLoopGroup
import os
from test import NativeResourceTest


class ScopedEnvironmentVariable(object):
    """
    Set environment variable for lifetime of this object.
    """

    def __init__(self, key, value):
        self.key = key
        self.prev_value = os.environ.get(key)
        os.environ[key] = value

    def __del__(self):
        if self.prev_value is None:
            del os.environ[self.key]
        else:
            os.environ[self.key] = self.prev_value


class TestProvider(NativeResourceTest):
    example_access_key_id = 'example_access_key_id'
    example_secret_access_key = 'example_secret_access_key'
    example_session_token = 'example_session_token'

    def test_static_provider(self):
        provider = CredentialsProvider.new_static(
            self.example_access_key_id,
            self.example_secret_access_key,
            self.example_session_token)

        future = provider.get_credentials()
        credentials = future.result()

        self.assertEqual(self.example_access_key_id, credentials.access_key_id)
        self.assertEqual(self.example_secret_access_key, credentials.secret_access_key)
        self.assertEqual(self.example_session_token, credentials.session_token)

    # TODO: test currently broken because None session_token comes back as empty string do to inconsistent use of
    # aws_byte_cursor by value/pointer in aws-c-auth APIs.
    #
    # def test_static_provider_no_session_token(self):
    #     provider = awscrt.auth.CredentialsProvider.new_static(
    #         self.example_access_key_id,
    #         self.example_secret_access_key)

    #     future = provider.get_credentials()
    #     credentials = future.result()

    #     self.assertEqual(self.example_access_key_id, credentials.access_key_id)
    #     self.assertEqual(self.example_secret_access_key, credentials.secret_access_key)
    #     self.assertIsNone(credentials.session_token)

    def test_default_provider(self):
        # Use environment variable to force specific credentials file
        scoped_env = ScopedEnvironmentVariable('AWS_SHARED_CREDENTIALS_FILE', 'test/resources/credentials_test')

        event_loop_group = EventLoopGroup()
        bootstrap = ClientBootstrap(event_loop_group)
        provider = CredentialsProvider.new_default_chain(bootstrap)

        future = provider.get_credentials()
        credentials = future.result()

        self.assertEqual('credentials_test_access_key_id', credentials.access_key_id)
        self.assertEqual('credentials_test_secret_access_key', credentials.secret_access_key)
        self.assertIsNone(credentials.session_token)

        del scoped_env
