# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from concurrent.futures import Future
from awscrt import mqtt5, io, auth
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


class Mqtt5TestCallbacks():
    def __init__(self):
        self.on_publish_receive_expected = 0
        self.on_publish_received_counter = 0
        self.last_exception = None

        self.negotiated_settings = None
        self.connack_packet = None
        self.publish_packet = None

        self.future_connection_success = Future()
        self.future_stopped = Future()
        self.future_connection_failure = Future()
        self.future_disconnection = Future()
        self.future_publish_received = Future()
        self.future_expected_publishes_received = Future()

        self.signing_config = None

    def ws_handshake_transform(self, transform_args):
        signing_future = auth.aws_sign_request(
            http_request=transform_args.http_request,
            signing_config=self.signing_config)
        signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))

    def on_publish_received(self, publish_received_data: mqtt5.PublishReceivedData):
        self.on_publish_received_counter += 1
        if self.future_publish_received and not self.future_publish_received.done():
            self.future_publish_received.set_result(publish_received_data.publish_packet)

        if self.on_publish_receive_expected > 0 and self.on_publish_received_counter == self.on_publish_receive_expected and not self.future_expected_publishes_received.done():
            self.future_expected_publishes_received.set_result(True)

    def on_lifecycle_stopped(self, lifecycle_stopped: mqtt5.LifecycleStoppedData):
        if self.future_stopped:
            self.future_stopped.set_result(None)

    def on_lifecycle_attempting_connect(self, lifecycle_attempting_connect: mqtt5.LifecycleAttemptingConnectData):
        pass

    def on_lifecycle_connection_success(self, lifecycle_connection_success: mqtt5.LifecycleConnectSuccessData):
        self.negotiated_settings = lifecycle_connection_success.negotiated_settings
        self.connack_packet = lifecycle_connection_success.connack_packet
        if self.future_connection_success:
            self.future_connection_success.set_result(lifecycle_connection_success)

    def on_lifecycle_connection_failure(self, lifecycle_connection_failure: mqtt5.LifecycleConnectFailureData):
        self.last_exception = lifecycle_connection_failure.exception
        if self.future_connection_failure:
            if self.future_connection_failure.done():
                pass
            else:
                self.future_connection_failure.set_result(lifecycle_connection_failure)

    def on_lifecycle_disconnection(self, lifecycle_disconnect_data: mqtt5.LifecycleDisconnectData):
        if self.future_disconnection:
            self.future_disconnection.set_result(lifecycle_disconnect_data)


class MqttConnectionTest(NativeResourceTest):
    def _create_client(
            self,
            client_options: mqtt5.ClientOptions = None,
            callbacks: Mqtt5TestCallbacks = None):

        default_host = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        if client_options is None:
            client_options = mqtt5.ClientOptions(
                host_name=default_host,
                port=8883
            )
        if client_options.connect_options is None:
            client_options.connect_options = mqtt5.ConnectPacket()
            client_options.connect_options.client_id = create_client_id()

        if callbacks is not None:
            client_options.on_publish_callback_fn = callbacks.on_publish_received
            client_options.on_lifecycle_event_stopped_fn = callbacks.on_lifecycle_stopped
            client_options.on_lifecycle_event_attempting_connect_fn = callbacks.on_lifecycle_attempting_connect
            client_options.on_lifecycle_event_connection_success_fn = callbacks.on_lifecycle_connection_success
            client_options.on_lifecycle_event_connection_failure_fn = callbacks.on_lifecycle_connection_failure
            client_options.on_lifecycle_event_disconnection_fn = callbacks.on_lifecycle_disconnection

        client = mqtt5.Client(client_options)
        return client

    def test_mqtt5_cred_pkcs12(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_PKCS12_KEY")
        input_key_password = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_PKCS12_KEY_PASSWORD")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_pkcs12(
            input_key,
            input_key_password
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_cred_windows_cert(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_windows = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_WINDOWS_CERT_STORE")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_windows_cert_store_path(
            input_windows
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_cred_pkcs11(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_pkcs11_lib = _get_env_variable("AWS_TEST_PKCS11_LIB")
        input_pkcs11_pin = _get_env_variable("AWS_TEST_PKCS11_PIN")
        input_pkcs11_token_label = _get_env_variable("AWS_TEST_PKCS11_TOKEN_LABEL")
        input_pkcs11_private_label = _get_env_variable("AWS_TEST_PKCS11_PKEY_LABEL")
        input_pkcs11_cert = _get_env_variable("AWS_TEST_PKCS11_CERT_FILE")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        test_pkcs11_lib = io.Pkcs11Lib(
            file=input_pkcs11_lib,
            behavior=io.Pkcs11Lib.InitializeFinalizeBehavior.STRICT)
        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_pkcs11(
            pkcs11_lib=test_pkcs11_lib,
            user_pin=input_pkcs11_pin,
            token_label=input_pkcs11_token_label,
            private_key_label=input_pkcs11_private_label,
            cert_file_path=input_pkcs11_cert
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_ws_cred_static(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_role_access_key = _get_env_variable("AWS_TEST_MQTT5_ROLE_CREDENTIAL_ACCESS_KEY")
        input_role_secret_access_key = _get_env_variable("AWS_TEST_MQTT5_ROLE_CREDENTIAL_SECRET_ACCESS_KEY")
        input_role_session_token = _get_env_variable("AWS_TEST_MQTT5_ROLE_CREDENTIAL_SESSION_TOKEN")
        input_region = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_REGION")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=443
        )
        credentials = auth.AwsCredentialsProvider.new_static(
            input_role_access_key,
            input_role_secret_access_key,
            input_role_session_token
        )
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
        client_options.websocket_handshake_transform = sign_function
        client_options.tls_ctx = io.ClientTlsContext(io.TlsContextOptions())

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_ws_cred_default(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_region = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_REGION")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=443
        )
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
        client_options.websocket_handshake_transform = sign_function
        client_options.tls_ctx = io.ClientTlsContext(io.TlsContextOptions())

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_ws_cred_cognito(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cognito_endpoint = _get_env_variable("AWS_TEST_MQTT5_COGNITO_ENDPOINT")
        input_cognito_identity = _get_env_variable("AWS_TEST_MQTT5_COGNITO_IDENTITY")
        input_region = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_REGION")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=443
        )
        credentials = auth.AwsCredentialsProvider.new_cognito(
            endpoint=input_cognito_endpoint,
            identity=input_cognito_identity,
            tls_ctx=io.ClientTlsContext(io.TlsContextOptions())
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
        client_options.websocket_handshake_transform = sign_function
        client_options.tls_ctx = io.ClientTlsContext(io.TlsContextOptions())

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_ws_cred_x509(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_X509_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_X509_KEY")
        input_x509_endpoint = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_X509_ENDPOINT")
        input_x509_role = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_X509_ROLE_ALIAS")
        input_x509_thing = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_X509_THING_NAME")
        input_region = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_REGION")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=443
        )
        x509_tls = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        credentials = auth.AwsCredentialsProvider.new_x509(
            endpoint=input_x509_endpoint,
            role_alias=input_x509_role,
            thing_name=input_x509_thing,
            tls_ctx=io.ClientTlsContext(x509_tls)
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
        client_options.websocket_handshake_transform = sign_function
        client_options.tls_ctx = io.ClientTlsContext(io.TlsContextOptions())

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_ws_cred_profile(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_profile_config = _get_env_variable("AWS_TEST_MQTT5_IOT_PROFILE_CONFIG")
        input_profile_cred = _get_env_variable("AWS_TEST_MQTT5_IOT_PROFILE_CREDENTIALS")
        input_region = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_REGION")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=443
        )
        credentials = auth.AwsCredentialsProvider.new_profile(
            config_filepath=input_profile_config,
            credentials_filepath=input_profile_cred
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
        client_options.websocket_handshake_transform = sign_function
        client_options.tls_ctx = io.ClientTlsContext(io.TlsContextOptions())

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_mqtt5_ws_cred_environment(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_access_key = _get_env_variable("AWS_TEST_MQTT5_ROLE_CREDENTIAL_ACCESS_KEY")
        input_secret_access_key = _get_env_variable("AWS_TEST_MQTT5_ROLE_CREDENTIAL_SECRET_ACCESS_KEY")
        input_session_token = _get_env_variable("AWS_TEST_MQTT5_ROLE_CREDENTIAL_SESSION_TOKEN")
        input_region = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_REGION")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=443
        )
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
        client_options.websocket_handshake_transform = sign_function
        client_options.tls_ctx = io.ClientTlsContext(io.TlsContextOptions())

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

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
