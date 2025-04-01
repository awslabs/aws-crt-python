# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from test import NativeResourceTest
from awscrt import io, mqtt5, mqtt_request_response, mqtt

from concurrent.futures import Future
import os
import unittest
import uuid

TIMEOUT = 30.0

def create_client_id():
    return f"aws-crt-python-unit-test-{uuid.uuid4()}"

def _get_env_variable(env_name):
    env_data = os.environ.get(env_name)
    if not env_data:
        raise unittest.SkipTest(f"test requires env var: {env_name}")
    return env_data

class MqttRequestResponse5TestCallbacks():
    def __init__(self):
        self.future_connection_success = Future()
        self.future_stopped = Future()

    def ws_handshake_transform(self, transform_args):
        transform_args.set_done()

    def on_publish_received(self, publish_received_data: mqtt5.PublishReceivedData):
        pass

    def on_lifecycle_stopped(self, lifecycle_stopped: mqtt5.LifecycleStoppedData):
        if self.future_stopped:
            self.future_stopped.set_result(None)

    def on_lifecycle_attempting_connect(self, lifecycle_attempting_connect: mqtt5.LifecycleAttemptingConnectData):
        pass

    def on_lifecycle_connection_success(self, lifecycle_connection_success: mqtt5.LifecycleConnectSuccessData):
        if self.future_connection_success:
            self.future_connection_success.set_result(lifecycle_connection_success)

    def on_lifecycle_connection_failure(self, lifecycle_connection_failure: mqtt5.LifecycleConnectFailureData):
        if self.future_connection_success:
            if self.future_connection_success.done():
                pass
            else:
                self.future_connection_success.set_exception(lifecycle_connection_failure.exception)

    def on_lifecycle_disconnection(self, lifecycle_disconnect_data: mqtt5.LifecycleDisconnectData):
        pass

class MqttRequestResponseClientTest(NativeResourceTest):

    def _create_client5(self):

        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        client_options.connect_options = mqtt5.ConnectPacket()
        client_options.connect_options.client_id = create_client_id()

        callbacks = MqttRequestResponse5TestCallbacks()
        client_options.on_lifecycle_event_stopped_fn = callbacks.on_lifecycle_stopped
        client_options.on_lifecycle_event_connection_success_fn = callbacks.on_lifecycle_connection_success
        client_options.on_lifecycle_event_connection_failure_fn = callbacks.on_lifecycle_connection_failure
        client_options.on_lifecycle_event_stopped_fn = callbacks.on_lifecycle_stopped

        protocol_client = mqtt5.Client(client_options)
        protocol_client.start()

        callbacks.future_connection_success.result(TIMEOUT)

        return protocol_client, callbacks

    def _shutdown5(self, protocol_client, callbacks):

        protocol_client.stop()
        callbacks.future_stopped.result(TIMEOUT)


    def _create_client311(self):

        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        tls_ctx = io.ClientTlsContext(tls_ctx_options)

        client = mqtt.Client(None, tls_ctx)

        protocol_client = mqtt.Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=8883,
            ping_timeout_ms=10000,
            keep_alive_secs=30
        )
        protocol_client.connect().result(TIMEOUT)

        return protocol_client

    def _shutdown311(self, protocol_client):
        protocol_client.disconnect().result(TIMEOUT)

    def _create_rr_client(self, protocol_client):
        rr_client_options = mqtt_request_response.RequestResponseClientOptions(2, 2)
        rr_client_options.operation_timeout_in_seconds = 30

        rr_client = mqtt_request_response.Client(protocol_client, rr_client_options)

        return rr_client

    def _create_rr_client_failure_invalid_config(self, protocol_client, max_request_response_subscriptions, max_streaming_subscriptions, operation_timeout_seconds):
        rr_client_options = mqtt_request_response.RequestResponseClientOptions(max_request_response_subscriptions, max_streaming_subscriptions)
        rr_client_options.operation_timeout_in_seconds = operation_timeout_seconds

        rr_client = mqtt_request_response.Client(protocol_client, rr_client_options)

        return rr_client

    def _create_get_shadow_request(self, thing_name, use_correlation_token):
        topic_prefix = f"$aws/things/{thing_name}/shadow/get"

        request_options = mqtt_request_response.RequestResponseOperationOptions(
            subscription_topic_filters=[f"{topic_prefix}/+"],
            response_paths=[
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/accepted"),
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/rejected")
            ],
            publish_topic = topic_prefix,
            payload="{}".encode()
        )

        if use_correlation_token:
            correlation_token = f"{uuid.uuid4()}"
            request_options.response_paths[0].correlation_token_json_path = "clientToken"
            request_options.response_paths[1].correlation_token_json_path = "clientToken"
            request_options.payload = f'{{"clientToken":"{correlation_token}"}}'.encode()
            request_options.correlation_token = correlation_token

        return request_options



    # ==============================================================
    #             CREATION TEST CASES
    # ==============================================================

    def test_client_creation_success5(self):
        (protocol_client, callbacks) = self._create_client5()
        rr_client = self._create_rr_client(protocol_client)

        self._shutdown5(protocol_client, callbacks)

    def test_client_creation_success311(self):
        protocol_client = self._create_client311()
        rr_client = self._create_rr_client(protocol_client)

        self._shutdown311(protocol_client)

    def test_client_creation_failure_zero_request_response_subscriptions(self):
        (protocol_client, callbacks) = self._create_client5()

        self.assertRaises(Exception, self._create_rr_client_failure_invalid_config, protocol_client, 0, 2, 30)

        self._shutdown5(protocol_client, callbacks)

    def test_client_creation_failure_negative_request_response_subscriptions(self):
        (protocol_client, callbacks) = self._create_client5()

        self.assertRaises(Exception, self._create_rr_client_failure_invalid_config, protocol_client, -1, 2, 30)

        self._shutdown5(protocol_client, callbacks)

    def test_client_creation_failure_negative_streaming_subscriptions(self):
        (protocol_client, callbacks) = self._create_client5()

        self.assertRaises(Exception, self._create_rr_client_failure_invalid_config, protocol_client, 2, -2, 30)

        self._shutdown5(protocol_client, callbacks)

    def test_client_creation_failure_negative_operation_timeout(self):
        (protocol_client, callbacks) = self._create_client5()

        self.assertRaises(Exception, self._create_rr_client_failure_invalid_config, protocol_client, 2, 2, -30)

        self._shutdown5(protocol_client, callbacks)


    def test_get_shadow_failure_no_such_shadow5(self):
        (protocol_client, callbacks) = self._create_client5()
        rr_client = self._create_rr_client(protocol_client)

        thing_name = f"tn-{uuid.uuid4()}"
        request_options = self._create_get_shadow_request(thing_name, True)

        response = rr_client.make_request(request_options)
        result = response.result()

        print("result={}".format(result))

        self._shutdown5(protocol_client, callbacks)


if __name__ == 'main':
    unittest.main()


