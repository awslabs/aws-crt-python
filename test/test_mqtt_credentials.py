# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, Pkcs11Lib, TlsContextOptions
from awscrt import auth
from awscrt.mqtt import Client, Connection
from test import NativeResourceTest
import os
import unittest
import uuid

TIMEOUT = 100.0


def _get_env_variable(env_name):
    env_data = os.environ.get(env_name)
    if not env_data:
        raise unittest.SkipTest(f"test requires env var: {env_name}")
    return env_data


def create_client_id():
    return 'aws-crt-python-unit-test-{0}'.format(uuid.uuid4())


class MqttConnectionTest(NativeResourceTest):

    def test_mqtt311_cred_pkcs12(self):
        tls_ctx_options = TlsContextOptions.create_client_with_mtls_pkcs12(
            _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_PKCS12_KEY"),
            _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_PKCS12_KEY_PASSWORD")
        )
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=8883)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_cred_windows_cert(self):
        tls_ctx_options = TlsContextOptions.create_client_with_mtls_windows_cert_store_path(
            _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_WINDOWS_PFX_CERT_NO_PASS")
        )
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=8883)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_cred_pkcs11(self):
        test_pkcs11_lib = Pkcs11Lib(
            file=_get_env_variable("AWS_TEST_PKCS11_LIB"),
            behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)
        tls_ctx_options = TlsContextOptions.create_client_with_mtls_pkcs11(
            pkcs11_lib=test_pkcs11_lib,
            user_pin=_get_env_variable("AWS_TEST_PKCS11_PIN"),
            token_label=_get_env_variable("AWS_TEST_PKCS11_TOKEN_LABEL"),
            private_key_label=_get_env_variable("AWS_TEST_PKCS11_PKEY_LABEL"),
            cert_file_path=_get_env_variable("AWS_TEST_PKCS11_CERT_FILE")
        )
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=8883)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_static(self):
        credentials = auth.AwsCredentialsProvider.new_static(
            _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_ACCESS_KEY"),
            _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SECRET_ACCESS_KEY"),
            _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SESSION_TOKEN")
        )
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION"),
            service="iotdevicegateway",
            omit_session_token=True
        )

        def sign_function(transform_args, **kwargs):
            signing_future = auth.aws_sign_request(
                http_request=transform_args.http_request,
                signing_config=signing_config)
            signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(TlsContextOptions()))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_default(self):
        credentials = auth.AwsCredentialsProvider.new_default_chain()
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION"),
            service="iotdevicegateway",
            omit_session_token=True
        )

        def sign_function(transform_args, **kwargs):
            signing_future = auth.aws_sign_request(
                http_request=transform_args.http_request,
                signing_config=signing_config)
            signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(TlsContextOptions()))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_cognito(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        credentials = auth.AwsCredentialsProvider.new_cognito(
            endpoint=_get_env_variable("AWS_TEST_MQTT311_COGNITO_ENDPOINT"),
            identity=_get_env_variable("AWS_TEST_MQTT311_COGNITO_IDENTITY"),
            tls_ctx=ClientTlsContext(TlsContextOptions()),
            client_bootstrap=bootstrap
        )

        def sign_function(transform_args, **kwargs):
            signing_config = auth.AwsSigningConfig(
                algorithm=auth.AwsSigningAlgorithm.V4,
                signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
                credentials_provider=credentials,
                region=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION"),
                service="iotdevicegateway",
                omit_session_token=True
            )
            signing_future = auth.aws_sign_request(
                http_request=transform_args.http_request,
                signing_config=signing_config)
            signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))

        client = Client(bootstrap, ClientTlsContext(TlsContextOptions()))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_x509(self):
        x509_tls = TlsContextOptions.create_client_with_mtls_from_path(
            _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_CERT"),
            _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_KEY")
        )
        credentials = auth.AwsCredentialsProvider.new_x509(
            endpoint=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_ENDPOINT"),
            role_alias=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_ROLE_ALIAS"),
            thing_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_THING_NAME"),
            tls_ctx=ClientTlsContext(x509_tls)
        )
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION"),
            service="iotdevicegateway",
            omit_session_token=True
        )

        def sign_function(transform_args, **kwargs):
            signing_future = auth.aws_sign_request(
                http_request=transform_args.http_request,
                signing_config=signing_config)
            signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(TlsContextOptions()))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_profile(self):
        credentials = auth.AwsCredentialsProvider.new_profile(
            config_filepath=_get_env_variable("AWS_TEST_MQTT311_IOT_PROFILE_CONFIG"),
            credentials_filepath=_get_env_variable("AWS_TEST_MQTT311_IOT_PROFILE_CREDENTIALS")
        )
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION"),
            service="iotdevicegateway",
            omit_session_token=True
        )
        def sign_function(transform_args, **kwargs):
            signing_future = auth.aws_sign_request(http_request=transform_args.http_request, signing_config=signing_config)
            signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(TlsContextOptions()))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_environment(self):
        # Cache the current credentials
        cache_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        cache_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        cache_token = os.environ.get("AWS_SESSION_TOKEN")
        # Set the environment variables from the static credentials
        os.environ["AWS_ACCESS_KEY_ID"] = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_ACCESS_KEY")
        os.environ["AWS_SECRET_ACCESS_KEY"] = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SECRET_ACCESS_KEY")
        os.environ["AWS_SESSION_TOKEN"] = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SESSION_TOKEN")
        # This should load the environment variables we just set
        credentials = auth.AwsCredentialsProvider.new_environment()
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION"),
            service="iotdevicegateway",
            omit_session_token=True
        )

        def sign_function(transform_args, **kwargs):
            signing_future = auth.aws_sign_request(
                http_request=transform_args.http_request,
                signing_config=signing_config)
            signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(TlsContextOptions()))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=_get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST"),
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

        # Set it back to the cached result
        if (cache_access_key != None):
            os.environ["AWS_ACCESS_KEY_ID"] = cache_access_key
        else:
            del os.environ["AWS_ACCESS_KEY_ID"]
        if (cache_secret_access_key != None):
            os.environ["AWS_SECRET_ACCESS_KEY"] = cache_secret_access_key
        else:
            del os.environ["AWS_SECRET_ACCESS_KEY"]
        if (cache_token != None):
            os.environ["AWS_SESSION_TOKEN"] = cache_token
        else:
            del os.environ["AWS_SESSION_TOKEN"]


if __name__ == 'main':
    unittest.main()
