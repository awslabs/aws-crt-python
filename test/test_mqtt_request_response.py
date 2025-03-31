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

        rr_client_options = mqtt_request_response.RequestResponseClientOptions(2, 2)
        rr_client_options.operation_timeout_in_seconds = 30

        rr_client = mqtt_request_response.Client(protocol_client, rr_client_options)

        return rr_client, protocol_client, callbacks

    def _shutdown5(self, rr_client, protocol_client, callbacks):

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

        rr_client_options = mqtt_request_response.RequestResponseClientOptions(2, 2)
        rr_client_options.operation_timeout_in_seconds = 30

        rr_client = mqtt_request_response.Client(protocol_client, rr_client_options)

        return rr_client, protocol_client

    def _shutdown311(self, rr_client, protocol_client):
        protocol_client.disconnect().result(TIMEOUT)


    # ==============================================================
    #             CREATION TEST CASES
    # ==============================================================

    def test_client_creation_success5(self):
        (rr_client, protocol_client, callbacks) = self._create_client5()

        self._shutdown5(rr_client, protocol_client, callbacks)

    def test_client_creation_success311(self):
        (rr_client, protocol_client) = self._create_client311()

        self._shutdown311(rr_client, protocol_client)


if __name__ == 'main':
    unittest.main()