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
from io import BytesIO
import os
from test import NativeResourceTest, TIMEOUT

EXAMPLE_ACCESS_KEY_ID = 'example_access_key_id'
EXAMPLE_SECRET_ACCESS_KEY = 'example_secret_access_key'
EXAMPLE_SESSION_TOKEN = 'example_session_token'


class ScopedEnvironmentVariable(object):
    """
    Set environment variable for lifetime of this object.
    """

    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.prev_value = os.environ.get(key)

    def __enter__(self):
        os.environ[self.key] = self.value

    def __exit__(self, type, value, tb):
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

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(EXAMPLE_SESSION_TOKEN == credentials.session_token)

    def test_create_no_session_token(self):
        credentials = awscrt.auth.AwsCredentials(EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(credentials.session_token is None)


class TestProvider(NativeResourceTest):
    def test_static_provider(self):
        provider = awscrt.auth.AwsCredentialsProvider.new_static(
            EXAMPLE_ACCESS_KEY_ID,
            EXAMPLE_SECRET_ACCESS_KEY,
            EXAMPLE_SESSION_TOKEN)

        future = provider.get_credentials()
        credentials = future.result(TIMEOUT)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(EXAMPLE_SESSION_TOKEN == credentials.session_token)

    # TODO: test currently broken because None session_token comes back as empty string do to inconsistent use of
    # aws_byte_cursor by value/pointer in aws-c-auth APIs.
    #
    # def test_static_provider_no_session_token(self):
    #     provider = AwsCredentialsProvider.new_static(
    #         self.example_access_key_id,
    #         self.example_secret_access_key)

    #     future = provider.get_credentials()
    #     credentials = future.result(TIMEOUT)

        # Don't use assertEqual(), which could log actual credentials if test fails.
    #     self.assertTrue(self.example_access_key_id == credentials.access_key_id)
    #     self.assertTrue(self.example_secret_access_key == credentials.secret_access_key)
    #     self.assertTrue(credentials.session_token is None)

    def test_default_provider(self):
        # Default credentials provider should pick up environment variables.
        with ScopedEnvironmentVariable('AWS_ACCESS_KEY_ID', EXAMPLE_ACCESS_KEY_ID), \
                ScopedEnvironmentVariable('AWS_SECRET_ACCESS_KEY', EXAMPLE_SECRET_ACCESS_KEY):

            event_loop_group = awscrt.io.EventLoopGroup()
            host_resolver = awscrt.io.DefaultHostResolver(event_loop_group)
            bootstrap = awscrt.io.ClientBootstrap(event_loop_group, host_resolver)
            provider = awscrt.auth.AwsCredentialsProvider.new_default_chain(bootstrap)

            future = provider.get_credentials()
            credentials = future.result(TIMEOUT)

            # Don't use assertEqual(), which could log actual credentials if test fails.
            self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
            self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
            self.assertTrue(credentials.session_token is None)


class TestSigningConfig(NativeResourceTest):
    def test_create(self):
        algorithm = awscrt.auth.AwsSigningAlgorithm.SigV4QueryParam
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)
        region = 'us-west-2'
        service = 'aws-suborbital-ion-cannon'
        date = datetime.datetime(year=2000, month=1, day=1)

        def should_sign_param(name):
            return not name.tolower().startswith('x-do-not-sign')

        use_double_uri_encode = True
        should_normalize_uri_path = False
        body_signing_type = awscrt.auth.AwsBodySigningConfigType.BodySigningOff

        cfg = awscrt.auth.AwsSigningConfig(algorithm=algorithm,
                                           credentials_provider=credentials_provider,
                                           region=region,
                                           service=service,
                                           date=date,
                                           should_sign_param=should_sign_param,
                                           use_double_uri_encode=use_double_uri_encode,
                                           should_normalize_uri_path=should_normalize_uri_path,
                                           body_signing_type=body_signing_type)

        self.assertIs(algorithm, cfg.algorithm)  # assert IS enum, not just EQUAL
        self.assertIs(credentials_provider, cfg.credentials_provider)
        self.assertEqual(region, cfg.region)
        self.assertEqual(service, cfg.service)
        self.assertEqual(date, cfg.date)
        self.assertIs(should_sign_param, cfg.should_sign_param)
        self.assertEqual(use_double_uri_encode, cfg.use_double_uri_encode)
        self.assertEqual(should_normalize_uri_path, cfg.should_normalize_uri_path)
        self.assertIs(body_signing_type, cfg.body_signing_type)

    def test_replace(self):
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)

        # nondefault values, to be sure they're carried over correctly
        orig_cfg = awscrt.auth.AwsSigningConfig(algorithm=awscrt.auth.AwsSigningAlgorithm.SigV4QueryParam,
                                                credentials_provider=credentials_provider,
                                                region='us-west-1',
                                                service='aws-suborbital-ion-cannon',
                                                date=datetime.datetime(year=2000, month=1, day=1),
                                                should_sign_param=lambda x: False,
                                                use_double_uri_encode=True,
                                                should_normalize_uri_path=False,
                                                body_signing_type=awscrt.auth.AwsBodySigningConfigType.BodySigningOff)

        # Call replace on single attribute, then assert that ONLY the one attribute differs
        def _replace_attr(name, value):
            new_cfg = orig_cfg.replace(**{name: value})
            self.assertIsNot(orig_cfg, new_cfg)  # must return new object

            self.assertEqual(value, getattr(new_cfg, name))  # must replace specified value

            # check that only the one attribute differs
            for attr in awscrt.auth.AwsSigningConfig._attributes:
                if attr == name:
                    self.assertNotEqual(getattr(orig_cfg, attr), getattr(new_cfg, attr),
                                        "replaced value should not match original")
                else:
                    self.assertEqual(getattr(orig_cfg, attr), getattr(new_cfg, attr),
                                     "value should match original")

        _replace_attr('algorithm', awscrt.auth.AwsSigningAlgorithm.SigV4Header)
        _replace_attr('credentials_provider',
                      awscrt.auth.AwsCredentialsProvider.new_static(EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY))
        _replace_attr('region', 'us-west-2')
        _replace_attr('service', 'aws-nothing-but-bees')
        _replace_attr('date', datetime.datetime(year=2001, month=1, day=1))
        _replace_attr('should_sign_param', lambda x: True)
        _replace_attr('use_double_uri_encode', False)
        _replace_attr('should_normalize_uri_path', True)
        _replace_attr('body_signing_type', awscrt.auth.AwsBodySigningConfigType.BodySigningOn)

        # check that we can replace multiple values at once
        new_cfg = orig_cfg.replace(region='us-west-3', service='aws-slow-blinking')
        self.assertEqual('us-west-3', new_cfg.region)
        self.assertEqual('aws-slow-blinking', new_cfg.service)

        self.assertEqual(orig_cfg.should_sign_param, new_cfg.should_sign_param)


# Test values copied from aws-c-auth/tests/aws-sig-v4-test-suite/get-vanilla"
SIGV4TEST_ACCESS_KEY_ID = 'AKIDEXAMPLE'
SIGV4TEST_SECRET_ACCESS_KEY = 'wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY'
SIGV4TEST_SESSION_TOKEN = None
SIGV4TEST_SERVICE = 'service'
SIGV4TEST_REGION = 'us-east-1'
SIGV4TEST_METHOD = 'GET'
SIGV4TEST_PATH = '/'
SIGV4TEST_DATE = datetime.datetime(year=2015, month=8, day=30, hour=12, minute=36, second=0, tzinfo=awscrt.auth._utc)
SIGV4TEST_UNSIGNED_HEADERS = [
    ('Host', 'example.amazonaws.com'),
]
SIGV4TEST_SIGNED_HEADERS = [
    ('Host',
     'example.amazonaws.com'),
    ('X-Amz-Date',
     '20150830T123600Z'),
    ('Authorization',
     'AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31')]


class TestSigner(NativeResourceTest):

    def test_signing_sigv4_headers(self):

        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            SIGV4TEST_ACCESS_KEY_ID, SIGV4TEST_SECRET_ACCESS_KEY, SIGV4TEST_SESSION_TOKEN)

        signing_config = awscrt.auth.AwsSigningConfig(
            algorithm=awscrt.auth.AwsSigningAlgorithm.SigV4Header,
            credentials_provider=credentials_provider,
            region=SIGV4TEST_REGION,
            service=SIGV4TEST_SERVICE,
            date=SIGV4TEST_DATE,
            body_signing_type=awscrt.auth.AwsBodySigningConfigType.BodySigningOff)

        http_request = awscrt.http.HttpRequest(
            method=SIGV4TEST_METHOD,
            path=SIGV4TEST_PATH,
            headers=awscrt.http.HttpHeaders(SIGV4TEST_UNSIGNED_HEADERS))

        signing_future = awscrt.auth.aws_sign_request(http_request, signing_config)

        signing_result = signing_future.result(TIMEOUT)

        self.assertIs(http_request, signing_result)  # should be same object

        self.assertEqual(SIGV4TEST_METHOD, http_request.method)
        self.assertEqual(SIGV4TEST_PATH, http_request.path)

        # existing headers should remain
        for prev_header in SIGV4TEST_UNSIGNED_HEADERS:
            self.assertIn(prev_header, http_request.headers)

        # signed headers must be present
        for signed_header in SIGV4TEST_SIGNED_HEADERS:
            self.assertIn(signed_header, http_request.headers)

    def test_signing_sigv4_body(self):

        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            SIGV4TEST_ACCESS_KEY_ID, SIGV4TEST_SECRET_ACCESS_KEY, SIGV4TEST_SESSION_TOKEN)

        signing_config = awscrt.auth.AwsSigningConfig(
            algorithm=awscrt.auth.AwsSigningAlgorithm.SigV4Header,
            credentials_provider=credentials_provider,
            region=SIGV4TEST_REGION,
            service=SIGV4TEST_SERVICE,
            date=SIGV4TEST_DATE,
            body_signing_type=awscrt.auth.AwsBodySigningConfigType.BodySigningOn)

        body_stream = BytesIO(b'hello')

        http_request = awscrt.http.HttpRequest(
            method='POST',
            path='/',
            headers=awscrt.http.HttpHeaders([('Host', 'example.amazonaws.com'), ('Content-Length', '5')]),
            body_stream=body_stream)

        signing_future = awscrt.auth.aws_sign_request(http_request, signing_config)

        signing_result = signing_future.result(TIMEOUT)

        self.assertIs(http_request, signing_result)  # should be same object

        self.assertEqual('2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
                         signing_result.headers.get('x-amz-content-sha256'))
        self.assertEqual(
            'AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=content-length;host;x-amz-content-sha256;x-amz-date, Signature=8e17c5b22b7bb28da47f44b08691c087a0993d0965bfab053376360790d44d6c',
            signing_result.headers.get('Authorization'))

        # stream should be seeked back to initial position
        self.assertEqual(0, body_stream.tell())
