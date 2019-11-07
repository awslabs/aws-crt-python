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
import awscrt.auth
import awscrt.io
import datetime
import os
from test import NativeResourceTest

EXAMPLE_ACCESS_KEY_ID = 'example_access_key_id'
EXAMPLE_SECRET_ACCESS_KEY = 'example_secret_access_key'
EXAMPLE_SESSION_TOKEN = 'example_session_token'


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


class TestCredentials(NativeResourceTest):
    def test_create(self):
        credentials = awscrt.auth.AwsCredentials(
            EXAMPLE_ACCESS_KEY_ID,
            EXAMPLE_SECRET_ACCESS_KEY,
            EXAMPLE_SESSION_TOKEN)
        self.assertEqual(EXAMPLE_ACCESS_KEY_ID, credentials.access_key_id)
        self.assertEqual(EXAMPLE_SECRET_ACCESS_KEY, credentials.secret_access_key)
        self.assertEqual(EXAMPLE_SESSION_TOKEN, credentials.session_token)

    def test_create_no_session_token(self):
        credentials = awscrt.auth.AwsCredentials(EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)
        self.assertEqual(EXAMPLE_ACCESS_KEY_ID, credentials.access_key_id)
        self.assertEqual(EXAMPLE_SECRET_ACCESS_KEY, credentials.secret_access_key)
        self.assertIsNone(credentials.session_token)


class TestProvider(NativeResourceTest):
    def test_static_provider(self):
        provider = awscrt.auth.StaticAwsCredentialsProvider(
            EXAMPLE_ACCESS_KEY_ID,
            EXAMPLE_SECRET_ACCESS_KEY,
            EXAMPLE_SESSION_TOKEN)

        future = provider.get_credentials()
        credentials = future.result()

        self.assertEqual(EXAMPLE_ACCESS_KEY_ID, credentials.access_key_id)
        self.assertEqual(EXAMPLE_SECRET_ACCESS_KEY, credentials.secret_access_key)
        self.assertEqual(EXAMPLE_SESSION_TOKEN, credentials.session_token)

    # TODO: test currently broken because None session_token comes back as empty string do to inconsistent use of
    # aws_byte_cursor by value/pointer in aws-c-auth APIs.
    #
    # def test_static_provider_no_session_token(self):
    #     provider = StaticAwsCredentialsProvider(
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

        event_loop_group = awscrt.io.EventLoopGroup()
        bootstrap = awscrt.io.ClientBootstrap(event_loop_group)
        provider = awscrt.auth.DefaultAwsCredentialsProviderChain(bootstrap)

        future = provider.get_credentials()
        credentials = future.result()

        self.assertEqual('credentials_test_access_key_id', credentials.access_key_id)
        self.assertEqual('credentials_test_secret_access_key', credentials.secret_access_key)
        self.assertIsNone(credentials.session_token)

        del scoped_env


class TestSigningConfig(NativeResourceTest):
    def test_create_default(self):
        # use default constructor
        cfg = awscrt.auth.AwsSigningConfig()
        self.assertIs(awscrt.auth.AwsSigningAlgorithm.Sigv4Headers, cfg.algorithm)  # assert IS enum, not just EQUAL
        self.assertIsNone(cfg.credentials_provider)
        self.assertIsNone(cfg.region)
        self.assertIsNone(cfg.service)
        self.assertTrue(isinstance(cfg.date, datetime.datetime))
        self.assertIsNone(cfg.should_sign_param)
        self.assertFalse(cfg.use_double_uri_encode)
        self.assertTrue(cfg.should_normalize_uri_path)
        self.assertTrue(cfg.sign_body)

    def test_create_specialized(self):
        # pass non-default value to every constructor arg
        algorithm = awscrt.auth.AwsSigningAlgorithm.Sigv4QueryParam
        credentials_provider = awscrt.auth.StaticAwsCredentialsProvider(
            EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)
        region = 'us-west-2'
        service = 'aws-suborbital-ion-canon'
        date = datetime.datetime.now()
        def should_sign_param(name): return not name.tolower().startswith('x-do-not-sign')
        use_double_uri_encode = True
        should_normalize_uri_path = False
        sign_body = False

        cfg = awscrt.auth.AwsSigningConfig(algorithm=algorithm,
                                           credentials_provider=credentials_provider,
                                           region=region,
                                           service=service,
                                           date=date,
                                           should_sign_param=should_sign_param,
                                           use_double_uri_encode=use_double_uri_encode,
                                           should_normalize_uri_path=should_normalize_uri_path,
                                           sign_body=sign_body)

        self.assertIs(algorithm, cfg.algorithm)  # assert IS enum, not just EQUAL
        self.assertIs(credentials_provider, cfg.credentials_provider)
        self.assertEqual(region, cfg.region)
        self.assertEqual(service, cfg.service)
        self.assertEqual(date, cfg.date)
        self.assertIs(should_sign_param, cfg.should_sign_param)
        self.assertEqual(use_double_uri_encode, cfg.use_double_uri_encode)
        self.assertEqual(should_normalize_uri_path, cfg.should_normalize_uri_path)
        self.assertEqual(sign_body, cfg.sign_body)
