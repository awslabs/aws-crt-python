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
        input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_PKCS12_KEY")
        input_key_password = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_PKCS12_KEY_PASSWORD")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        tls_ctx_options = TlsContextOptions.create_client_with_mtls_pkcs12(
            input_key,
            input_key_password
        )
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=8883)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_cred_windows_cert(self):
        input_windows = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_WINDOWS_CERT_STORE")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        tls_ctx_options = TlsContextOptions.create_client_with_mtls_windows_cert_store_path(
            input_windows
        )
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=8883)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_cred_pkcs11(self):
        input_pkcs11_lib = _get_env_variable("AWS_TEST_PKCS11_LIB")
        input_pkcs11_pin = _get_env_variable("AWS_TEST_PKCS11_PIN")
        input_pkcs11_token_label = _get_env_variable("AWS_TEST_PKCS11_TOKEN_LABEL")
        input_pkcs11_private_key = _get_env_variable("AWS_TEST_PKCS11_PKEY_LABEL")
        input_pkcs11_cert = _get_env_variable("AWS_TEST_PKCS11_CERT_FILE")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        test_pkcs11_lib = Pkcs11Lib(
            file=input_pkcs11_lib,
            behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)
        tls_ctx_options = TlsContextOptions.create_client_with_mtls_pkcs11(
            pkcs11_lib=test_pkcs11_lib,
            user_pin=input_pkcs11_pin,
            token_label=input_pkcs11_token_label,
            private_key_label=input_pkcs11_private_key,
            cert_file_path=input_pkcs11_cert
        )
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=8883)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_static(self):
        input_role_access_key = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_ACCESS_KEY")
        input_role_secret_key = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SECRET_ACCESS_KEY")
        input_role_session_token = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SESSION_TOKEN")
        input_role_region = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        credentials = auth.AwsCredentialsProvider.new_static(
            input_role_access_key,
            input_role_secret_key,
            input_role_session_token
        )
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=input_role_region,
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
            host_name=input_host_name,
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_default(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        input_region = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION")

        credentials = auth.AwsCredentialsProvider.new_default_chain()

        def sign_function(transform_args, **kwargs):
            signing_config = auth.AwsSigningConfig(
                algorithm=auth.AwsSigningAlgorithm.V4,
                signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
                credentials_provider=credentials,
                region=input_region,
                service="iotdevicegateway",
                omit_session_token=True
            )
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
            host_name=input_host_name,
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_cognito(self):
        input_cognito_endpoint = _get_env_variable("AWS_TEST_MQTT311_COGNITO_ENDPOINT")
        input_cognito_identity = _get_env_variable("AWS_TEST_MQTT311_COGNITO_IDENTITY")
        input_region = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        credentials = auth.AwsCredentialsProvider.new_cognito(
            endpoint=input_cognito_endpoint,
            identity=input_cognito_identity,
            tls_ctx=ClientTlsContext(TlsContextOptions()),
            client_bootstrap=bootstrap
        )

        def sign_function(transform_args, **kwargs):
            signing_config = auth.AwsSigningConfig(
                algorithm=auth.AwsSigningAlgorithm.V4,
                signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
                credentials_provider=credentials,
                region=input_region,
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
            host_name=input_host_name,
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_x509(self):
        input_x509_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_CERT")
        input_x509_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_KEY")
        input_x509_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_ENDPOINT")
        input_x509_role = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_ROLE_ALIAS")
        input_x509_thing = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_X509_THING_NAME")
        input_region = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        x509_tls = TlsContextOptions.create_client_with_mtls_from_path(
            input_x509_cert,
            input_x509_key
        )
        credentials = auth.AwsCredentialsProvider.new_x509(
            endpoint=input_x509_endpoint,
            role_alias=input_x509_role,
            thing_name=input_x509_thing,
            tls_ctx=ClientTlsContext(x509_tls)
        )
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=input_region,
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
            host_name=input_host_name,
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_profile(self):
        input_profile_config = _get_env_variable("AWS_TEST_MQTT311_IOT_PROFILE_CONFIG")
        input_profile_cred = _get_env_variable("AWS_TEST_MQTT311_IOT_PROFILE_CREDENTIALS")
        input_region = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        credentials = auth.AwsCredentialsProvider.new_profile(
            config_filepath=input_profile_config,
            credentials_filepath=input_profile_cred
        )
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=input_region,
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
            host_name=input_host_name,
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_ws_cred_environment(self):
        input_access_key = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_ACCESS_KEY")
        input_secret_access_key = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SECRET_ACCESS_KEY")
        input_session_token = _get_env_variable("AWS_TEST_MQTT311_ROLE_CREDENTIAL_SESSION_TOKEN")
        input_region = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_REGION")
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        # Cache the current credentials
        cache_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        cache_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        cache_token = os.environ.get("AWS_SESSION_TOKEN")
        # Set the environment variables from the static credentials
        os.environ["AWS_ACCESS_KEY_ID"] = input_access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = input_secret_access_key
        os.environ["AWS_SESSION_TOKEN"] = input_session_token
        # This should load the environment variables we just set
        credentials = auth.AwsCredentialsProvider.new_environment()
        signing_config = auth.AwsSigningConfig(
            algorithm=auth.AwsSigningAlgorithm.V4,
            signature_type=auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
            credentials_provider=credentials,
            region=input_region,
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
            host_name=input_host_name,
            port=int(443),
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

        # Set it back to the cached result
        if (cache_access_key is not None):
            os.environ["AWS_ACCESS_KEY_ID"] = cache_access_key
        else:
            del os.environ["AWS_ACCESS_KEY_ID"]
        if (cache_secret_access_key is not None):
            os.environ["AWS_SECRET_ACCESS_KEY"] = cache_secret_access_key
        else:
            del os.environ["AWS_SECRET_ACCESS_KEY"]
        if (cache_token is not None):
            os.environ["AWS_SESSION_TOKEN"] = cache_token
        else:
            del os.environ["AWS_SESSION_TOKEN"]


if __name__ == 'main':
    unittest.main()
