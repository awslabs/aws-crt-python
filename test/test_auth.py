# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt.auth
import awscrt.io
import datetime
from io import BytesIO
import os
import sys
from test import NativeResourceTest, TIMEOUT
import time
import unittest

EXAMPLE_ACCESS_KEY_ID = 'example_access_key_id'
EXAMPLE_SECRET_ACCESS_KEY = 'example_secret_access_key'
EXAMPLE_SESSION_TOKEN = 'example_session_token'
EXAMPLE_SESSION_EXPIRATION = datetime.datetime.fromtimestamp(1609911816, tz=datetime.timezone.utc)


class ScopedEnvironmentVariable:
    """
    Set environment variable for lifetime of this object.
    """

    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.prev_value = os.environ.get(key)

    def __enter__(self):
        if self.value is None:
            os.environ.pop(self.key, None)
        else:
            os.environ[self.key] = self.value

    def __exit__(self, type, value, tb):
        if self.prev_value is None:
            os.environ.pop(self.key, None)
        else:
            os.environ[self.key] = self.prev_value


class TestCredentials(NativeResourceTest):
    def test_create(self):
        credentials = awscrt.auth.AwsCredentials(
            EXAMPLE_ACCESS_KEY_ID,
            EXAMPLE_SECRET_ACCESS_KEY,
            EXAMPLE_SESSION_TOKEN,
            EXAMPLE_SESSION_EXPIRATION)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(EXAMPLE_SESSION_TOKEN == credentials.session_token)
        self.assertTrue(EXAMPLE_SESSION_EXPIRATION == credentials.expiration)

    def test_create_no_session_token(self):
        credentials = awscrt.auth.AwsCredentials(EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(credentials.session_token is None)

    def test_create_no_expiration(self):
        credentials = awscrt.auth.AwsCredentials(EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(credentials.expiration is None)


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

    def test_static_provider_no_session_token(self):
        provider = awscrt.auth.AwsCredentialsProvider.new_static(
            EXAMPLE_ACCESS_KEY_ID,
            EXAMPLE_SECRET_ACCESS_KEY)

        future = provider.get_credentials()
        credentials = future.result(TIMEOUT)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(credentials.session_token is None)

    def test_default_provider(self):
        # Default credentials provider should pick up environment variables.
        with ScopedEnvironmentVariable('AWS_ACCESS_KEY_ID', EXAMPLE_ACCESS_KEY_ID), \
                ScopedEnvironmentVariable('AWS_SECRET_ACCESS_KEY', EXAMPLE_SECRET_ACCESS_KEY),\
                ScopedEnvironmentVariable('AWS_SESSION_TOKEN', None):

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

    def test_profile_provider(self):
        # Profile provider should pick up the profile file to provide the credentials.
        profile_name = "crt_user"
        credentials_filepath = "test/resources/example_profile"
        event_loop_group = awscrt.io.EventLoopGroup()
        host_resolver = awscrt.io.DefaultHostResolver(event_loop_group)
        bootstrap = awscrt.io.ClientBootstrap(event_loop_group, host_resolver)
        provider = awscrt.auth.AwsCredentialsProvider.new_profile(
            bootstrap, profile_name=profile_name, credentials_filepath=credentials_filepath)

        future = provider.get_credentials()
        credentials = future.result(TIMEOUT)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
        self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
        self.assertTrue(credentials.session_token is None)

    def test_environment_provider(self):
        with ScopedEnvironmentVariable('AWS_ACCESS_KEY_ID', EXAMPLE_ACCESS_KEY_ID), \
                ScopedEnvironmentVariable('AWS_SECRET_ACCESS_KEY', EXAMPLE_SECRET_ACCESS_KEY), \
                ScopedEnvironmentVariable('AWS_SESSION_TOKEN', EXAMPLE_SESSION_TOKEN):

            provider = awscrt.auth.AwsCredentialsProvider.new_environment()
            credentials = provider.get_credentials().result(TIMEOUT)

            # Don't use assertEqual(), which could log actual credentials if test fails.
            self.assertTrue(EXAMPLE_ACCESS_KEY_ID == credentials.access_key_id)
            self.assertTrue(EXAMPLE_SECRET_ACCESS_KEY == credentials.secret_access_key)
            self.assertTrue(EXAMPLE_SESSION_TOKEN == credentials.session_token)

    def test_chain_provider(self):
        provider = awscrt.auth.AwsCredentialsProvider.new_chain([
            awscrt.auth.AwsCredentialsProvider.new_static('id_a', 'secret_a'),
            awscrt.auth.AwsCredentialsProvider.new_static('id_b', 'secret_b'),
        ])
        credentials = provider.get_credentials().result(TIMEOUT)
        self.assertTrue('id_a' == credentials.access_key_id)
        self.assertTrue('secret_a' == credentials.secret_access_key)
        self.assertTrue(credentials.session_token is None)

    def test_chain_provider_bad_args(self):
        with self.assertRaises(TypeError):
            awscrt.auth.AwsCredentialsProvider.new_chain(None)

        with self.assertRaises(ValueError):
            awscrt.auth.AwsCredentialsProvider.new_chain([])

        with self.assertRaises(TypeError):
            provider = awscrt.auth.AwsCredentialsProvider.new_chain([
                awscrt.auth.AwsCredentialsProvider.new_static('id_a', 'secret_a'),
                "I am not an AwsCredentialsProvider",
            ])

    def test_process_provider(self):
        with ScopedEnvironmentVariable("AWS_CONFIG_FILE", "test/resources/example_config"):
            if sys.platform == 'win32':
                profile = 'test_process_provider_win'
            else:
                profile = 'test_process_provider'
            provider = awscrt.auth.AwsCredentialsProvider.new_process(profile)
            credentials = provider.get_credentials().result(TIMEOUT)

            # Don't use assertEqual(), which could log actual credentials if test fails.
            self.assertTrue('process_access_key_id' == credentials.access_key_id)
            self.assertTrue('process_secret_access_key' == credentials.secret_access_key)
            self.assertTrue(credentials.session_token is None)

    def test_delegate_provider(self):
        def delegate_get_credentials():
            return awscrt.auth.AwsCredentials("accesskey", "secretAccessKey", "sessionToken")

        provider = awscrt.auth.AwsCredentialsProvider.new_delegate(delegate_get_credentials)
        credentials = provider.get_credentials().result(TIMEOUT)

        # Don't use assertEqual(), which could log actual credentials if test fails.
        self.assertTrue('accesskey' == credentials.access_key_id)
        self.assertTrue('secretAccessKey' == credentials.secret_access_key)
        self.assertTrue('sessionToken' == credentials.session_token)

    def test_delegate_provider_exception(self):
        # delegate that raises exception should result in exception
        def delegate_get_credentials():
            raise Exception("purposefully thrown exception")

        provider = awscrt.auth.AwsCredentialsProvider.new_delegate(delegate_get_credentials)

        with self.assertRaises(Exception):
            credentials_future = provider.get_credentials()
            credentials = credentials_future.result(TIMEOUT)

    def test_delegate_provider_exception_from_bad_return_type(self):
        # delegate that returns wrong type should result in exception
        def delegate_get_credentials():
            return "purposefully return wrong type"

        provider = awscrt.auth.AwsCredentialsProvider.new_delegate(delegate_get_credentials)

        with self.assertRaises(Exception):
            credentials_future = provider.get_credentials()
            credentials = credentials_future.result(TIMEOUT)


@unittest.skipUnless(os.environ.get('AWS_TEST_MQTT311_COGNITO_IDENTITY') and os.environ.get('AWS_TEST_MQTT311_COGNITO_ENDPOINT'),
                     'set env var to run test: AWS_TEST_MQTT311_COGNITO_IDENTITY and AWS_TEST_MQTT311_COGNITO_ENDPOINT')
class CognitoCredentialsProviderTest(NativeResourceTest):

    def test_unauthenticated(self):
        identity = os.environ.get('AWS_TEST_MQTT311_COGNITO_IDENTITY')
        identity_endpoint = os.environ.get('AWS_TEST_MQTT311_COGNITO_ENDPOINT')
        tls_opts = awscrt.io.TlsContextOptions()
        tls_context = awscrt.io.ClientTlsContext(tls_opts)

        provider = awscrt.auth.AwsCredentialsProvider.new_cognito(
            endpoint=identity_endpoint,
            identity=identity,
            tls_ctx=tls_context
        )

        self.assertIsNotNone(provider)
        credentials = provider.get_credentials().result(TIMEOUT)
        self.assertIsNotNone(credentials)

    def test_cognito_provider_create_exception_bad_login(self):
        identity = os.environ.get('AWS_TEST_MQTT311_COGNITO_IDENTITY')
        identity_endpoint = os.environ.get('AWS_TEST_MQTT311_COGNITO_ENDPOINT')
        tls_opts = awscrt.io.TlsContextOptions()
        tls_context = awscrt.io.ClientTlsContext(tls_opts)

        with self.assertRaises(Exception):
            provider = awscrt.auth.AwsCredentialsProvider.new_cognito(
                endpoint=identity_endpoint,
                identity=identity,
                tls_ctx=tls_context,
                logins=[('provider1', 5), ('provider2', ['List not string'])]
            )

            self.assertIsNone(provider)

    def test_maximal_create(self):
        identity = os.environ.get('AWS_TEST_MQTT311_COGNITO_IDENTITY')
        identity_endpoint = os.environ.get('AWS_TEST_MQTT311_COGNITO_ENDPOINT')
        tls_opts = awscrt.io.TlsContextOptions()
        tls_context = awscrt.io.ClientTlsContext(tls_opts)

        provider = awscrt.auth.AwsCredentialsProvider.new_cognito(
            endpoint=identity_endpoint,
            identity=identity,
            tls_ctx=tls_context,
            logins=[('provider1', 'token1'), ('provide2', 'token2')],
            custom_role_arn='not-a-real-arn'
        )

        self.assertIsNotNone(provider)


@unittest.skipUnless(os.environ.get('AWS_TESTING_COGNITO_IDENTITY') and os.environ.get('AWS_TEST_MQTT311_COGNITO_ENDPOINT')
                     and os.environ.get('AWS_TEST_HTTP_PROXY_HOST') and os.environ.get('AWS_TEST_HTTP_PROXY_PORT'),
                     'set env var to run test: AWS_TESTING_COGNITO_IDENTITY, AWS_TEST_MQTT311_COGNITO_ENDPOINT, '
                     'AWS_TEST_HTTP_PROXY_HOST, and AWS_TEST_HTTP_PROXY_PORT')
class CognitoCredentialsProviderProxyTest(NativeResourceTest):

    def test_unauthenticated(self):
        identity = os.environ.get('AWS_TESTING_COGNITO_IDENTITY')
        identity_endpoint = os.environ.get('AWS_TEST_MQTT311_COGNITO_ENDPOINT')
        tls_opts = awscrt.io.TlsContextOptions()
        tls_context = awscrt.io.ClientTlsContext(tls_opts)
        http_proxy_options = awscrt.http.HttpProxyOptions(
            os.environ.get('AWS_TEST_HTTP_PROXY_HOST'),
            int(os.environ.get('AWS_TEST_HTTP_PROXY_PORT', '0')))

        provider = awscrt.auth.AwsCredentialsProvider.new_cognito(
            endpoint=identity_endpoint,
            identity=identity,
            tls_ctx=tls_context,
            http_proxy_options=http_proxy_options
        )

        self.assertIsNotNone(provider)
        credentials = provider.get_credentials().result(TIMEOUT)
        self.assertIsNotNone(credentials)


class TestSigningConfig(NativeResourceTest):
    def test_create(self):
        algorithm = awscrt.auth.AwsSigningAlgorithm.V4
        signature_type = awscrt.auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)
        region = 'us-west-2'
        service = 'aws-suborbital-ion-cannon'
        date = datetime.datetime(year=2000, month=1, day=1)

        def should_sign_header(name):
            return not name.tolower().startswith('x-do-not-sign')

        use_double_uri_encode = False
        should_normalize_uri_path = False
        signed_body_value = awscrt.auth.AwsSignedBodyValue.EMPTY_SHA256
        signed_body_header_type = awscrt.auth.AwsSignedBodyHeaderType.X_AMZ_CONTENT_SHA_256
        expiration_in_seconds = 123
        omit_session_token = True

        cfg = awscrt.auth.AwsSigningConfig(algorithm=algorithm,
                                           signature_type=signature_type,
                                           credentials_provider=credentials_provider,
                                           region=region,
                                           service=service,
                                           date=date,
                                           should_sign_header=should_sign_header,
                                           use_double_uri_encode=use_double_uri_encode,
                                           should_normalize_uri_path=should_normalize_uri_path,
                                           signed_body_value=signed_body_value,
                                           signed_body_header_type=signed_body_header_type,
                                           expiration_in_seconds=expiration_in_seconds,
                                           omit_session_token=omit_session_token)

        self.assertIs(algorithm, cfg.algorithm)  # assert IS enum, not just EQUAL
        self.assertIs(signature_type, cfg.signature_type)
        self.assertIs(credentials_provider, cfg.credentials_provider)
        self.assertEqual(region, cfg.region)
        self.assertEqual(service, cfg.service)
        self.assertEqual(date, cfg.date)
        self.assertIs(should_sign_header, cfg.should_sign_header)
        self.assertEqual(use_double_uri_encode, cfg.use_double_uri_encode)
        self.assertEqual(should_normalize_uri_path, cfg.should_normalize_uri_path)
        self.assertEqual(signed_body_value, cfg.signed_body_value)
        self.assertIs(signed_body_header_type, cfg.signed_body_header_type)
        self.assertEqual(expiration_in_seconds, cfg.expiration_in_seconds)
        self.assertEqual(omit_session_token, cfg.omit_session_token)

    def test_replace(self):
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)

        # nondefault values, to be sure they're carried over correctly
        orig_cfg = awscrt.auth.AwsSigningConfig(
            algorithm=awscrt.auth.AwsSigningAlgorithm.V4,
            signature_type=awscrt.auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials_provider,
            region='us-west-1',
            service='aws-suborbital-ion-cannon',
            date=datetime.datetime(
                year=2000,
                month=1,
                day=1),
            should_sign_header=lambda x: False,
            use_double_uri_encode=False,
            should_normalize_uri_path=False,
            signed_body_value=awscrt.auth.AwsSignedBodyValue.EMPTY_SHA256,
            signed_body_header_type=awscrt.auth.AwsSignedBodyHeaderType.X_AMZ_CONTENT_SHA_256,
            expiration_in_seconds=123,
            omit_session_token=True)

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

        _replace_attr('signature_type', awscrt.auth.AwsSignatureType.HTTP_REQUEST_HEADERS)
        _replace_attr('credentials_provider',
                      awscrt.auth.AwsCredentialsProvider.new_static(EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY))
        _replace_attr('region', 'us-west-2')
        _replace_attr('service', 'aws-nothing-but-bees')
        _replace_attr('date', datetime.datetime(year=2001, month=1, day=1))
        _replace_attr('should_sign_header', lambda x: True)
        _replace_attr('use_double_uri_encode', True)
        _replace_attr('should_normalize_uri_path', True)
        _replace_attr('signed_body_value', awscrt.auth.AwsSignedBodyValue.UNSIGNED_PAYLOAD)
        _replace_attr('signed_body_header_type', awscrt.auth.AwsSignedBodyHeaderType.NONE)
        _replace_attr('expiration_in_seconds', 987)
        _replace_attr('omit_session_token', False)

        # check that we can replace multiple values at once
        new_cfg = orig_cfg.replace(region='us-west-3', service='aws-slow-blinking')
        self.assertEqual('us-west-3', new_cfg.region)
        self.assertEqual('aws-slow-blinking', new_cfg.service)

        self.assertEqual(orig_cfg.should_sign_header, new_cfg.should_sign_header)

    def test_special_defaults(self):
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            EXAMPLE_ACCESS_KEY_ID, EXAMPLE_SECRET_ACCESS_KEY)

        config = awscrt.auth.AwsSigningConfig(
            algorithm=awscrt.auth.AwsSigningAlgorithm.V4,
            signature_type=awscrt.auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials_provider,
            region='us-west-1',
            service='aws-suborbital-ion-cannon')

        # for things in the C layer where zeroed values mean "defaults please",
        # the python layer chooses to use None.
        # make sure None is coming back and not zeroes or empty strings.
        self.assertIsNone(config.signed_body_value)
        self.assertIsNone(config.expiration_in_seconds)

        # if no date specified, now should be used.
        # check that config.date has something very close to now.
        self.assertAlmostEqual(time.time(), config.date.timestamp(), delta=2.0)


SIGV4TEST_ACCESS_KEY_ID = 'AKIDEXAMPLE'
SIGV4TEST_SECRET_ACCESS_KEY = 'wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY'
SIGV4TEST_SESSION_TOKEN = None
SIGV4TEST_SERVICE = 'service'
SIGV4TEST_REGION = 'us-east-1'
SIGV4TEST_DATE = datetime.datetime(
    year=2015,
    month=8,
    day=30,
    hour=12,
    minute=36,
    second=0,
    tzinfo=datetime.timezone.utc)


class TestSigner(NativeResourceTest):

    def test_signing_sigv4_headers(self):
        # Test values copied from aws-c-auth/tests/aws-sig-v4-test-suite/get-vanilla"
        self._test_signing_sigv4_headers(
            method='GET',
            path='/',
            unsigned_headers=[('Host', 'example.amazonaws.com')],
            signed_headers=[
                ('Host',
                 'example.amazonaws.com'),
                ('X-Amz-Date',
                 '20150830T123600Z'),
                ('Authorization',
                 'AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31')])

    def _test_signing_sigv4_headers(self, method, path, unsigned_headers, signed_headers):
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            SIGV4TEST_ACCESS_KEY_ID, SIGV4TEST_SECRET_ACCESS_KEY, SIGV4TEST_SESSION_TOKEN)

        signing_config = awscrt.auth.AwsSigningConfig(
            algorithm=awscrt.auth.AwsSigningAlgorithm.V4,
            signature_type=awscrt.auth.AwsSignatureType.HTTP_REQUEST_HEADERS,
            credentials_provider=credentials_provider,
            region=SIGV4TEST_REGION,
            service=SIGV4TEST_SERVICE,
            date=SIGV4TEST_DATE)

        http_request = awscrt.http.HttpRequest(
            method=method,
            path=path,
            headers=awscrt.http.HttpHeaders(unsigned_headers))

        signing_future = awscrt.auth.aws_sign_request(http_request, signing_config)

        signing_result = signing_future.result(TIMEOUT)

        self.assertIs(http_request, signing_result)  # should be same object

        self.assertEqual(method, http_request.method)
        self.assertEqual(path, http_request.path)

        # existing headers should remain
        for prev_header in unsigned_headers:
            self.assertIn(prev_header, http_request.headers)

        # signed headers must be present
        for signed_header in signed_headers:
            self.assertIn(signed_header, http_request.headers)

    def test_signing_sigv4_body(self):
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            SIGV4TEST_ACCESS_KEY_ID, SIGV4TEST_SECRET_ACCESS_KEY, SIGV4TEST_SESSION_TOKEN)

        signing_config = awscrt.auth.AwsSigningConfig(
            algorithm=awscrt.auth.AwsSigningAlgorithm.V4,
            signature_type=awscrt.auth.AwsSignatureType.HTTP_REQUEST_HEADERS,
            credentials_provider=credentials_provider,
            region=SIGV4TEST_REGION,
            service=SIGV4TEST_SERVICE,
            date=SIGV4TEST_DATE,
            signed_body_header_type=awscrt.auth.AwsSignedBodyHeaderType.X_AMZ_CONTENT_SHA_256)

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

    def test_signing_sigv4_utf8(self):
        # Test values copied from aws-c-auth/tests/aws-sig-v4-test-suite/get-utf8"
        self._test_signing_sigv4_headers(
            method='GET',
            path=u'/\u1234',  # "/ሴ"
            unsigned_headers=[('Host', 'example.amazonaws.com')],
            signed_headers=[
                ('Host',
                 'example.amazonaws.com'),
                ('X-Amz-Date',
                 '20150830T123600Z'),
                ('Authorization',
                 'AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=8318018e0b0f223aa2bbf98705b62bb787dc9c0e678f255a891fd03141be5d85')])

    def test_signing_sigv4a_headers(self):
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_static(
            SIGV4TEST_ACCESS_KEY_ID, SIGV4TEST_SECRET_ACCESS_KEY, SIGV4TEST_SESSION_TOKEN)

        signing_config = awscrt.auth.AwsSigningConfig(
            algorithm=awscrt.auth.AwsSigningAlgorithm.V4_ASYMMETRIC,
            signature_type=awscrt.auth.AwsSignatureType.HTTP_REQUEST_HEADERS,
            credentials_provider=credentials_provider,
            region=SIGV4TEST_REGION,
            service=SIGV4TEST_SERVICE,
            date=SIGV4TEST_DATE)

        http_request = awscrt.http.HttpRequest('GET', '/')
        http_request.headers.add('Host', 'example.amazonaws.com')

        signing_future = awscrt.auth.aws_sign_request(http_request, signing_config)
        signed_request = signing_future.result(TIMEOUT)

        auth_header_value = signed_request.headers.get('Authorization')
        self.assertIsNotNone(auth_header_value)
        self.assertTrue(auth_header_value.startswith(
            'AWS4-ECDSA-P256-SHA256 Credential=AKIDEXAMPLE/20150830/service/aws4_request, SignedHeaders=host;x-amz-date;x-amz-region-set, Signature='))
