# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from concurrent.futures import Future
from awscrt import mqtt5, io, http, exceptions
from test import NativeResourceTest
from threading import Lock
import os
import unittest
import uuid
import time

"""
# Environmental variables used by mqtt5 bindings tests

# AWS_TEST_MQTT5_DIRECT_MQTT_HOST - host to connect to in direct mqtt tests
# AWS_TEST_MQTT5_DIRECT_MQTT_PORT - port to connect to in direct mqtt tests
# AWS_TEST_MQTT5_DIRECT_MQTT_BASIC_AUTH_HOST - host to connect to in direct mqtt basic authentication tests
# AWS_TEST_MQTT5_DIRECT_MQTT_BASIC_AUTH_PORT - port to connect to in direct mqtt basic authentication tests
# AWS_TEST_MQTT5_DIRECT_MQTT_TLS_HOST - host to connect to in direct mqtt tls tests
# AWS_TEST_MQTT5_DIRECT_MQTT_TLS_PORT - port to connect to in direct mqtt tls tests
# AWS_TEST_MQTT5_WS_MQTT_HOST - host to connect to in websocket tests
# AWS_TEST_MQTT5_WS_MQTT_PORT - port to connect to in websocket tests
# AWS_TEST_MQTT5_WS_MQTT_BASIC_AUTH_HOST - host to connect to in websocket basic authentication tests
# AWS_TEST_MQTT5_WS_MQTT_BASIC_AUTH_PORT - port to connect to in websocket basic authentication tests
# AWS_TEST_MQTT5_WS_MQTT_TLS_HOST - host to connect to in websocket tls tests
# AWS_TEST_MQTT5_WS_MQTT_TLS_PORT - port to connect to in websocket tls tests
# AWS_TEST_MQTT5_IOT_CORE_HOST - host to connect to in MTLS tests
# AWS_TEST_MQTT5_BASIC_AUTH_USERNAME - username to use in basic authentication tests
# AWS_TEST_MQTT5_BASIC_AUTH_PASSWORD - password to use in basic authentication tests
# AWS_TEST_MQTT5_PROXY_HOST - name of http proxy host to use in proxy-based tests
# AWS_TEST_MQTT5_PROXY_PORT - port of http proxy host to use in proxy-based tests
# AWS_TEST_MQTT5_CERTIFICATE_FILE - certificate file path
# AWS_TEST_MQTT5_KEY_FILE - private key file path
# AWS_TEST_MQTT5_IOT_KEY_PATH - private key file path for MTLS tests
# AWS_TEST_MQTT5_IOT_CERTIFICATE_PATH - certificate file path for MTLS tests

"""

TIMEOUT = 100.0


def _get_env_variable(env_name):
    env_data = os.environ.get(env_name)
    if not env_data:
        raise unittest.SkipTest(f"test requires env var: {env_name}")
    return env_data


def create_client_id():
    return f"aws-crt-python-unit-test-{uuid.uuid4()}"


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

    def ws_handshake_transform(self, transform_args):
        transform_args.set_done()

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


class Mqtt5ClientTest(NativeResourceTest):

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

    # ==============================================================
    #             CREATION TEST CASES
    # ==============================================================

    def test_client_creation_minimum(self):
        client = self._create_client()

    def test_client_creation_maximum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")

        user_properties = []
        user_properties.append(mqtt5.UserProperty(name="name1", value="value1"))
        user_properties.append(mqtt5.UserProperty(name="name2", value="value2"))

        publish_packet = mqtt5.PublishPacket(
            payload="TEST_PAYLOAD",
            qos=mqtt5.QoS.AT_LEAST_ONCE,
            retain=False,
            topic="TEST_TOPIC",
            payload_format_indicator=mqtt5.PayloadFormatIndicator.AWS_MQTT5_PFI_UTF8,
            message_expiry_interval_sec=10,
            topic_alias=1,
            response_topic="TEST_RESPONSE_TOPIC",
            correlation_data="TEST_CORRELATION_DATA",
            content_type="TEST_CONTENT_TYPE",
            user_properties=user_properties
        )

        connect_options = mqtt5.ConnectPacket(
            keep_alive_interval_sec=10,
            client_id="TEST_CLIENT",
            username="USERNAME",
            password="PASSWORD",
            session_expiry_interval_sec=100,
            request_response_information=1,
            request_problem_information=1,
            receive_maximum=1000,
            maximum_packet_size=10000,
            will_delay_interval_sec=1000,
            will=publish_packet,
            user_properties=user_properties
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
            session_behavior=mqtt5.ClientSessionBehaviorType.CLEAN,
            extended_validation_and_flow_control_options=mqtt5.ExtendedValidationAndFlowControlOptions.AWS_IOT_CORE_DEFAULTS,
            offline_queue_behavior=mqtt5.ClientOperationQueueBehaviorType.FAIL_ALL_ON_DISCONNECT,
            retry_jitter_mode=mqtt5.ExponentialBackoffJitterMode.DECORRELATED,
            min_reconnect_delay_ms=100,
            max_reconnect_delay_ms=50000,
            min_connected_time_to_reset_reconnect_delay_ms=1000,
            ping_timeout_ms=1000,
            connack_timeout_ms=1000,
            ack_timeout_sec=100)
        client = self._create_client(client_options=client_options)

    # ==============================================================
    #             DIRECT CONNECT TEST CASES
    # ==============================================================

    def test_direct_connect_minimum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_direct_connect_basic_auth(self):
        input_username = _get_env_variable("AWS_TEST_MQTT5_BASIC_AUTH_USERNAME")
        input_password = _get_env_variable("AWS_TEST_MQTT5_BASIC_AUTH_PASSWORD")
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_BASIC_AUTH_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_BASIC_AUTH_PORT"))

        connect_options = mqtt5.ConnectPacket(
            client_id=create_client_id(),
            username=input_username,
            password=input_password
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_direct_connect_tls(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_TLS_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        tls_ctx_options = io.TlsContextOptions()
        tls_ctx_options.verify_peer = False
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_direct_connect_mutual_tls(self):
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

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_direct_connect_http_proxy_tls(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_TLS_PORT"))
        input_proxy_host = _get_env_variable("AWS_TEST_MQTT5_PROXY_HOST")
        input_proxy_port = int(_get_env_variable("AWS_TEST_MQTT5_PROXY_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        tls_ctx_options = io.TlsContextOptions()
        tls_ctx_options.verify_peer = False
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        http_proxy_options = http.HttpProxyOptions(
            host_name=input_proxy_host,
            port=input_proxy_port
        )
        http_proxy_options.connection_type = http.HttpProxyConnectionType.Tunneling
        http_proxy_options.auth_type = http.HttpProxyAuthenticationType.Nothing
        client_options.http_proxy_options = http_proxy_options

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_direct_connect_maximum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        user_properties = []
        user_properties.append(mqtt5.UserProperty(name="name1", value="value1"))
        user_properties.append(mqtt5.UserProperty(name="name2", value="value2"))

        publish_packet = mqtt5.PublishPacket(
            payload="TEST_PAYLOAD",
            qos=mqtt5.QoS.AT_LEAST_ONCE,
            retain=False,
            topic="TEST_TOPIC",
            payload_format_indicator=mqtt5.PayloadFormatIndicator.AWS_MQTT5_PFI_UTF8,
            message_expiry_interval_sec=10,
            topic_alias=1,
            response_topic="TEST_RESPONSE_TOPIC",
            correlation_data="TEST_CORRELATION_DATA",
            content_type="TEST_CONTENT_TYPE",
            user_properties=user_properties
        )
        connect_options = mqtt5.ConnectPacket(
            keep_alive_interval_sec=10,
            client_id=create_client_id(),
            session_expiry_interval_sec=100,
            request_response_information=1,
            request_problem_information=1,
            receive_maximum=1000,
            maximum_packet_size=10000,
            will_delay_interval_sec=1000,
            will=publish_packet,
            user_properties=user_properties
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options,
            session_behavior=mqtt5.ClientSessionBehaviorType.CLEAN,
            extended_validation_and_flow_control_options=mqtt5.ExtendedValidationAndFlowControlOptions.AWS_IOT_CORE_DEFAULTS,
            offline_queue_behavior=mqtt5.ClientOperationQueueBehaviorType.FAIL_ALL_ON_DISCONNECT,
            retry_jitter_mode=mqtt5.ExponentialBackoffJitterMode.DECORRELATED,
            min_reconnect_delay_ms=100,
            max_reconnect_delay_ms=50000,
            min_connected_time_to_reset_reconnect_delay_ms=1000,
            ping_timeout_ms=1000,
            connack_timeout_ms=1000,
            ack_timeout_sec=100)

        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             WEBSOCKET CONNECT TEST CASES
    # ==============================================================

    def test_websocket_connect_minimum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_WS_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_WS_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        callbacks = Mqtt5TestCallbacks()
        client_options.websocket_handshake_transform = callbacks.ws_handshake_transform

        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_websocket_connect_basic_auth(self):
        input_username = _get_env_variable("AWS_TEST_MQTT5_BASIC_AUTH_USERNAME")
        input_password = _get_env_variable("AWS_TEST_MQTT5_BASIC_AUTH_PASSWORD")
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_WS_MQTT_BASIC_AUTH_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_WS_MQTT_BASIC_AUTH_PORT"))

        connect_options = mqtt5.ConnectPacket(
            client_id=create_client_id(),
            username=input_username,
            password=input_password
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options
        )
        callbacks = Mqtt5TestCallbacks()
        client_options.websocket_handshake_transform = callbacks.ws_handshake_transform

        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_websocket_connect_tls(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_WS_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_WS_MQTT_TLS_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        tls_ctx_options = io.TlsContextOptions()
        tls_ctx_options.verify_peer = False
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client_options.websocket_handshake_transform = callbacks.ws_handshake_transform

        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # TODO test_websocket_connect_sigv4 against IoT Core

    def test_websocket_connect_http_proxy_tls(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_WS_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_WS_MQTT_TLS_PORT"))
        input_proxy_host = _get_env_variable("AWS_TEST_MQTT5_PROXY_HOST")
        input_proxy_port = int(_get_env_variable("AWS_TEST_MQTT5_PROXY_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        tls_ctx_options = io.TlsContextOptions()
        tls_ctx_options.verify_peer = False
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        http_proxy_options = http.HttpProxyOptions(
            host_name=input_proxy_host,
            port=input_proxy_port
        )
        http_proxy_options.connection_type = http.HttpProxyConnectionType.Tunneling
        http_proxy_options.auth_type = http.HttpProxyAuthenticationType.Nothing
        client_options.http_proxy_options = http_proxy_options

        callbacks = Mqtt5TestCallbacks()
        client_options.websocket_handshake_transform = callbacks.ws_handshake_transform

        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_websocket_connect_maximum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_WS_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_WS_MQTT_PORT"))

        user_properties = []
        user_properties.append(mqtt5.UserProperty(name="name1", value="value1"))
        user_properties.append(mqtt5.UserProperty(name="name2", value="value2"))

        publish_packet = mqtt5.PublishPacket(
            payload="TEST_PAYLOAD",
            qos=mqtt5.QoS.AT_LEAST_ONCE,
            retain=False,
            topic="TEST_TOPIC",
            payload_format_indicator=mqtt5.PayloadFormatIndicator.AWS_MQTT5_PFI_UTF8,
            message_expiry_interval_sec=10,
            topic_alias=1,
            response_topic="TEST_RESPONSE_TOPIC",
            correlation_data="TEST_CORRELATION_DATA",
            content_type="TEST_CONTENT_TYPE",
            user_properties=user_properties
        )
        connect_options = mqtt5.ConnectPacket(
            keep_alive_interval_sec=10,
            client_id=create_client_id(),
            session_expiry_interval_sec=100,
            request_response_information=1,
            request_problem_information=1,
            receive_maximum=1000,
            maximum_packet_size=10000,
            will_delay_interval_sec=1000,
            will=publish_packet,
            user_properties=user_properties
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options,
            session_behavior=mqtt5.ClientSessionBehaviorType.CLEAN,
            extended_validation_and_flow_control_options=mqtt5.ExtendedValidationAndFlowControlOptions.AWS_IOT_CORE_DEFAULTS,
            offline_queue_behavior=mqtt5.ClientOperationQueueBehaviorType.FAIL_ALL_ON_DISCONNECT,
            retry_jitter_mode=mqtt5.ExponentialBackoffJitterMode.DECORRELATED,
            min_reconnect_delay_ms=100,
            max_reconnect_delay_ms=50000,
            min_connected_time_to_reset_reconnect_delay_ms=1000,
            ping_timeout_ms=1000,
            connack_timeout_ms=1000,
            ack_timeout_sec=100)
        callbacks = Mqtt5TestCallbacks()
        client_options.websocket_handshake_transform = callbacks.ws_handshake_transform
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             NEGATIVE CONNECT TEST CASES
    # ==============================================================

    def test_connect_with_invalid_host_name(self):
        client_options = mqtt5.ClientOptions(
            host_name="badhost",
            port=1883
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_failure.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_connect_with_invalid_port(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=444
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_failure.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_connect_with_invalid_port_for_websocket_connection(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_WS_MQTT_HOST")
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=1883
        )
        callbacks = Mqtt5TestCallbacks()
        client_options.websocket_handshake_transform = callbacks.ws_handshake_transform
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_failure.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_connect_with_socket_timeout(self):
        client_options = mqtt5.ClientOptions(
            host_name="www.example.com",
            port=81
        )
        client_options.connack_timeout_ms = 200
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_failure.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_connect_with_incorrect_basic_authentication_credentials(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_BASIC_AUTH_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_BASIC_AUTH_PORT"))

        connect_options = mqtt5.ConnectPacket(
            client_id=create_client_id(),
            username="bad username",
            password="bad password"
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_failure.result(TIMEOUT)
        self.assertEqual(str(callbacks.last_exception), str(exceptions.from_code(5150)))
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # TODO test_websocket_handshake_failure

    def test_double_client_id_failure(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))
        shared_client_id = create_client_id()

        connect_options = mqtt5.ConnectPacket(client_id=shared_client_id)
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options
        )
        callbacks = Mqtt5TestCallbacks()
        client1 = self._create_client(client_options=client_options, callbacks=callbacks)

        callbacks2 = Mqtt5TestCallbacks()
        client2 = self._create_client(client_options=client_options, callbacks=callbacks2)

        client1.start()
        callbacks.future_connection_success.result(TIMEOUT)

        client2.start()

        callbacks.future_disconnection.result(TIMEOUT)

        client1.stop()
        callbacks.future_stopped.result(TIMEOUT)
        client2.stop()
        callbacks2.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             NEGATIVE DATA INPUT TEST CASES
    # ==============================================================

    def test_negative_connect_packet_properties(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")

        connect_options = mqtt5.ConnectPacket(
            keep_alive_interval_sec=-10,
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            session_expiry_interval_sec=-100,
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            receive_maximum=-1000,
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            maximum_packet_size=-10000,
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            will_delay_interval_sec=-1000,
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

    def test_overflow_connect_packet_properties(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        connect_options = mqtt5.ConnectPacket(
            keep_alive_interval_sec=65536
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            session_expiry_interval_sec=4294967296
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            receive_maximum=65536
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            maximum_packet_size=4294967296
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

        connect_options = mqtt5.ConnectPacket(
            will_delay_interval_sec=4294967296
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            connect_options=connect_options,
        )

        with self.assertRaises(OverflowError) as cm:
            self._create_client(client_options=client_options)

    def test_negative_disconnect_packet_properties(self):
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
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        disconnect_packet = mqtt5.DisconnectPacket(session_expiry_interval_sec=-1)

        with self.assertRaises(OverflowError) as cm:
            client.stop(disconnect_packet=disconnect_packet)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_negative_publish_packet_properties(self):
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
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        publish_packet = mqtt5.PublishPacket(message_expiry_interval_sec=-1)
        with self.assertRaises(OverflowError) as cm:
            client.publish(publish_packet=publish_packet)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_negative_subscribe_packet_properties(self):
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
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter="test1", qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(subscription_identifier=-1, subscriptions=subscriptions)

        with self.assertRaises(OverflowError) as cm:
            client.subscribe(subscribe_packet=subscribe_packet)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             NEGOTIATED SETTINGS TEST CASES
    # ==============================================================

    def test_negotiated_settings_minimal_settings(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        connect_options = mqtt5.ConnectPacket(
            session_expiry_interval_sec=600000
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        self.assertIsNotNone(callbacks.negotiated_settings)
        self.assertEqual(callbacks.negotiated_settings.session_expiry_interval_sec, 600000)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_negotiated_settings_maximum_settings(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        client_id = create_client_id()
        connect_options = mqtt5.ConnectPacket(
            client_id=client_id,
            session_expiry_interval_sec=600,
            keep_alive_interval_sec=1000
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        self.assertIsNotNone(callbacks.negotiated_settings)
        self.assertIsNotNone(callbacks.connack_packet)
        self.assertIsNone(callbacks.connack_packet.assigned_client_identifier)
        self.assertEqual(callbacks.negotiated_settings.session_expiry_interval_sec, 600)
        self.assertEqual(callbacks.negotiated_settings.server_keep_alive_sec, 1000)
        self.assertEqual(callbacks.negotiated_settings.maximum_qos, mqtt5.QoS.AT_LEAST_ONCE)
        self.assertEqual(callbacks.negotiated_settings.receive_maximum_from_server, 10)
        self.assertEqual(callbacks.negotiated_settings.maximum_packet_size_to_server, 268435460)
        self.assertEqual(callbacks.negotiated_settings.topic_alias_maximum_to_server, 10)
        self.assertEqual(callbacks.negotiated_settings.topic_alias_maximum_to_client, 0)
        self.assertTrue(callbacks.negotiated_settings.retain_available)
        self.assertTrue(callbacks.negotiated_settings.wildcard_subscriptions_available)
        self.assertTrue(callbacks.negotiated_settings.subscription_identifiers_available)
        self.assertTrue(callbacks.negotiated_settings.shared_subscriptions_available)
        self.assertFalse(callbacks.negotiated_settings.rejoined_session)
        self.assertEqual(callbacks.negotiated_settings.client_id, client_id)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_negotiated_settings_server_limit(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        uint32_max = 4294967295
        uint16_max = 65535

        connect_options = mqtt5.ConnectPacket(
            session_expiry_interval_sec=uint32_max,
            receive_maximum=uint16_max,
            keep_alive_interval_sec=uint16_max,
            maximum_packet_size=uint32_max
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port,
            connect_options=connect_options
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        self.assertIsNotNone(callbacks.negotiated_settings)
        self.assertNotEqual(callbacks.negotiated_settings.receive_maximum_from_server, uint16_max)
        self.assertNotEqual(callbacks.negotiated_settings.maximum_packet_size_to_server, uint32_max)
        self.assertEqual(callbacks.negotiated_settings.server_keep_alive_sec, uint16_max)
        self.assertEqual(callbacks.negotiated_settings.session_expiry_interval_sec, uint32_max)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             OPERATION TEST CASES
    # ==============================================================

    def test_operation_sub_unsub(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id
        payload = "Hello World"

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        callbacks.on_publish_receive_expected = 1

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = client.subscribe(subscribe_packet=subscribe_packet)
        suback_packet = subscribe_future.result(TIMEOUT)
        self.assertIsInstance(suback_packet, mqtt5.SubackPacket)

        publish_packet = mqtt5.PublishPacket(
            payload=payload,
            topic=topic_filter,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        publish_future = client.publish(publish_packet=publish_packet)
        publish_completion_data = publish_future.result(TIMEOUT)
        puback_packet = publish_completion_data.puback
        self.assertIsInstance(puback_packet, mqtt5.PubackPacket)

        callbacks.future_expected_publishes_received.result(TIMEOUT)

        topic_filters = []
        topic_filters.append(topic_filter)
        unsubscribe_packet = mqtt5.UnsubscribePacket(topic_filters=topic_filters)
        unsubscribe_future = client.unsubscribe(unsubscribe_packet)
        unsuback_packet = unsubscribe_future.result(TIMEOUT)
        self.assertIsInstance(unsuback_packet, mqtt5.UnsubackPacket)

        publish_future = client.publish(publish_packet=publish_packet)
        publish_completion_data = publish_future.result(TIMEOUT)
        puback_packet = publish_completion_data.puback
        self.assertIsInstance(puback_packet, mqtt5.PubackPacket)

        self.assertEqual(callbacks.on_publish_received_counter, 1)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    sub1_callbacks = False
    sub2_callbacks = False
    total_callbacks = 0
    all_packets_received = Future()
    mutex = Lock()
    received_subscriptions = [0] * 10

    def subscriber1_callback(self, publish_received_data: mqtt5.PublishReceivedData):
        self.mutex.acquire()
        var = publish_received_data.publish_packet.payload
        self.received_subscriptions[int(var)] = 1
        self.sub1_callbacks = True
        self.total_callbacks = self.total_callbacks + 1
        if self.total_callbacks == 10:
            self.all_packets_received.set_result(None)
        self.mutex.release()

    def subscriber2_callback(self, publish_received_data: mqtt5.PublishReceivedData):
        self.mutex.acquire()
        var = publish_received_data.publish_packet.payload
        self.received_subscriptions[int(var)] = 1
        self.sub2_callbacks = True
        self.total_callbacks = self.total_callbacks + 1
        if self.total_callbacks == 10:
            self.all_packets_received.set_result(None)
        self.mutex.release()

    def test_operation_shared_subscription(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id_subscriber1 = create_client_id()
        client_id_subscriber2 = create_client_id()
        client_id_publisher = create_client_id()

        testTopic = "test/MQTT5_Binding_Python_" + client_id_publisher
        sharedTopicfilter = "$share/crttest/test/MQTT5_Binding_Python_" + client_id_publisher

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )

        # subscriber 1
        connect_subscriber1_options = mqtt5.ConnectPacket(client_id=client_id_subscriber1)
        subscriber1_generic_callback = Mqtt5TestCallbacks()
        subscriber1_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            tls_ctx=io.ClientTlsContext(tls_ctx_options),
            connect_options=connect_subscriber1_options,
            on_publish_callback_fn=self.subscriber1_callback,
            on_lifecycle_event_stopped_fn=subscriber1_generic_callback.on_lifecycle_stopped,
            on_lifecycle_event_attempting_connect_fn=subscriber1_generic_callback.on_lifecycle_attempting_connect,
            on_lifecycle_event_connection_success_fn=subscriber1_generic_callback.on_lifecycle_connection_success,
            on_lifecycle_event_connection_failure_fn=subscriber1_generic_callback.on_lifecycle_connection_failure
        )
        subscriber1_client = mqtt5.Client(client_options=subscriber1_options)

        # subscriber 2
        connect_subscriber2_options = mqtt5.ConnectPacket(client_id=client_id_subscriber2)
        subscriber2_generic_callback = Mqtt5TestCallbacks()
        subscriber2_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            tls_ctx=io.ClientTlsContext(tls_ctx_options),
            connect_options=connect_subscriber2_options,
            on_publish_callback_fn=self.subscriber2_callback,
            on_lifecycle_event_stopped_fn=subscriber2_generic_callback.on_lifecycle_stopped,
            on_lifecycle_event_attempting_connect_fn=subscriber2_generic_callback.on_lifecycle_attempting_connect,
            on_lifecycle_event_connection_success_fn=subscriber2_generic_callback.on_lifecycle_connection_success,
            on_lifecycle_event_connection_failure_fn=subscriber2_generic_callback.on_lifecycle_connection_failure
        )
        subscriber2_client = mqtt5.Client(client_options=subscriber2_options)

        # publisher
        connect_publisher_options = mqtt5.ConnectPacket(client_id=client_id_publisher)
        publisher_generic_callback = Mqtt5TestCallbacks()

        publisher_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            tls_ctx=io.ClientTlsContext(tls_ctx_options),
            connect_options=connect_publisher_options,
            on_lifecycle_event_stopped_fn=publisher_generic_callback.on_lifecycle_stopped,
            on_lifecycle_event_attempting_connect_fn=publisher_generic_callback.on_lifecycle_attempting_connect,
            on_lifecycle_event_connection_success_fn=publisher_generic_callback.on_lifecycle_connection_success,
            on_lifecycle_event_connection_failure_fn=publisher_generic_callback.on_lifecycle_connection_failure
        )
        publisher_client = mqtt5.Client(client_options=publisher_options)

        print("Connecting all 3 clients\n")
        subscriber1_client.start()
        subscriber1_generic_callback.future_connection_success.result(TIMEOUT)

        subscriber2_client.start()
        subscriber2_generic_callback.future_connection_success.result(TIMEOUT)

        publisher_client.start()
        publisher_generic_callback.future_connection_success.result(TIMEOUT)
        print("All clients connected\n")

        # Subscriber 1
        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=sharedTopicfilter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = subscriber1_client.subscribe(subscribe_packet=subscribe_packet)
        suback_packet1 = subscribe_future.result(TIMEOUT)
        self.assertIsInstance(suback_packet1, mqtt5.SubackPacket)

        # Subscriber 2
        subscriptions2 = []
        subscriptions2.append(mqtt5.Subscription(topic_filter=sharedTopicfilter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet2 = mqtt5.SubscribePacket(
            subscriptions=subscriptions2)
        subscribe_future2 = subscriber2_client.subscribe(subscribe_packet=subscribe_packet2)
        suback_packet2 = subscribe_future2.result(TIMEOUT)
        self.assertIsInstance(suback_packet2, mqtt5.SubackPacket)

        publishes = 10
        for x in range(0, publishes):
            packet = mqtt5.PublishPacket(
                payload=f"{x}",
                qos=mqtt5.QoS.AT_LEAST_ONCE,
                topic=testTopic
            )
            publish_future = publisher_client.publish(packet)
            publish_future.result(TIMEOUT)

        self.all_packets_received.result(TIMEOUT)

        topic_filters = []
        topic_filters.append(testTopic)
        unsubscribe_packet = mqtt5.UnsubscribePacket(topic_filters=testTopic)

        unsubscribe_future = subscriber1_client.unsubscribe(unsubscribe_packet)
        unsuback_packet = unsubscribe_future.result(TIMEOUT)
        self.assertIsInstance(unsuback_packet, mqtt5.UnsubackPacket)

        unsubscribe_future = subscriber2_client.unsubscribe(unsubscribe_packet)
        unsuback_packet = unsubscribe_future.result(TIMEOUT)
        self.assertIsInstance(unsuback_packet, mqtt5.UnsubackPacket)

        self.assertEqual(self.sub1_callbacks, True)
        self.assertEqual(self.sub2_callbacks, True)
        self.assertEqual(self.total_callbacks, 10)

        for e in self.received_subscriptions:
            self.assertEqual(e, 1)

        subscriber1_client.stop()
        subscriber1_generic_callback.future_stopped.result(TIMEOUT)

        subscriber2_client.stop()
        subscriber2_generic_callback.future_stopped.result(TIMEOUT)

        publisher_client.stop()
        publisher_generic_callback.future_stopped.result(TIMEOUT)

    def test_operation_will(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id_publisher = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id_publisher

        will_packet = mqtt5.PublishPacket(
            payload="TEST WILL",
            qos=mqtt5.QoS.AT_LEAST_ONCE,
            topic=topic_filter
        )

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )

        client_options1 = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options1.connect_options = mqtt5.ConnectPacket(client_id=client_id_publisher,
                                                              will_delay_interval_sec=0,
                                                              will=will_packet)
        client_options1.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks1 = Mqtt5TestCallbacks()
        client1 = self._create_client(client_options=client_options1, callbacks=callbacks1)
        client1.start()
        callbacks1.future_connection_success.result(TIMEOUT)

        client_options2 = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options2.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options2.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks2 = Mqtt5TestCallbacks()
        client2 = self._create_client(client_options=client_options2, callbacks=callbacks2)
        client2.start()
        callbacks2.future_connection_success.result(TIMEOUT)

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = client2.subscribe(subscribe_packet=subscribe_packet)
        suback_packet = subscribe_future.result(TIMEOUT)
        self.assertIsInstance(suback_packet, mqtt5.SubackPacket)

        disconnect_packet = mqtt5.DisconnectPacket(reason_code=mqtt5.DisconnectReasonCode.DISCONNECT_WITH_WILL_MESSAGE)
        client1.stop(disconnect_packet=disconnect_packet)
        callbacks1.future_stopped.result(TIMEOUT)

        received_will = callbacks2.future_publish_received.result(TIMEOUT)
        self.assertIsInstance(received_will, mqtt5.PublishPacket)
        client2.stop()
        callbacks2.future_stopped.result(TIMEOUT)

    def do_will_correlation_data_test(self, outbound_correlation_data_bytes, outbound_correlation_data,
                                      expected_correlation_data_bytes, expected_correlation_data):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id_publisher = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id_publisher

        payload = "TEST WILL"
        payload_bytes = payload.encode("utf-8")

        will_packet = mqtt5.PublishPacket(
            payload="TEST WILL",
            qos=mqtt5.QoS.AT_LEAST_ONCE,
            topic=topic_filter,
            correlation_data_bytes=outbound_correlation_data_bytes,
            correlation_data=outbound_correlation_data
        )

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )

        client_options1 = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options1.connect_options = mqtt5.ConnectPacket(client_id=client_id_publisher,
                                                              will_delay_interval_sec=0,
                                                              will=will_packet)
        client_options1.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks1 = Mqtt5TestCallbacks()
        client1 = self._create_client(client_options=client_options1, callbacks=callbacks1)
        client1.start()
        callbacks1.future_connection_success.result(TIMEOUT)

        client_options2 = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options2.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options2.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks2 = Mqtt5TestCallbacks()
        client2 = self._create_client(client_options=client_options2, callbacks=callbacks2)
        client2.start()
        callbacks2.future_connection_success.result(TIMEOUT)

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = client2.subscribe(subscribe_packet=subscribe_packet)
        suback_packet = subscribe_future.result(TIMEOUT)
        self.assertIsInstance(suback_packet, mqtt5.SubackPacket)

        disconnect_packet = mqtt5.DisconnectPacket(reason_code=mqtt5.DisconnectReasonCode.DISCONNECT_WITH_WILL_MESSAGE)
        client1.stop(disconnect_packet=disconnect_packet)
        callbacks1.future_stopped.result(TIMEOUT)

        received_will = callbacks2.future_publish_received.result(TIMEOUT)
        self.assertIsInstance(received_will, mqtt5.PublishPacket)
        self.assertEqual(received_will.payload, payload_bytes)
        self.assertEqual(received_will.correlation_data_bytes, expected_correlation_data_bytes)
        self.assertEqual(received_will.correlation_data, expected_correlation_data)

        client2.stop()
        callbacks2.future_stopped.result(TIMEOUT)

    def test_will_correlation_data_bytes_binary(self):
        correlation_data = bytearray(os.urandom(64))
        self.do_will_correlation_data_test(correlation_data, None, correlation_data, None)

    def test_will_correlation_data_bytes_string(self):
        correlation_data = "CorrelationData"
        correlation_data_as_bytes = correlation_data.encode('utf-8')
        self.do_correlation_data_test(correlation_data, None, correlation_data_as_bytes, correlation_data)

    def test_will_correlation_data_binary(self):
        correlation_data = bytearray(os.urandom(64))
        self.do_correlation_data_test(None, correlation_data, correlation_data, None)

    def test_will_correlation_data_string(self):
        correlation_data = "CorrelationData"
        correlation_data_as_bytes = correlation_data.encode('utf-8')
        self.do_correlation_data_test(None, correlation_data, correlation_data_as_bytes, correlation_data)

    def test_will_correlation_data_bytes_binary_precedence(self):
        correlation_data = bytearray(os.urandom(64))
        self.do_correlation_data_test(correlation_data, "Ignored", correlation_data, None)

    def test_operation_binary_publish(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id
        payload = bytearray(os.urandom(256))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = client.subscribe(subscribe_packet=subscribe_packet)
        suback_packet = subscribe_future.result(TIMEOUT)
        self.assertIsInstance(suback_packet, mqtt5.SubackPacket)

        publish_packet = mqtt5.PublishPacket(
            payload=payload,
            topic=topic_filter,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        publish_future = client.publish(publish_packet=publish_packet)
        publish_completion_data = publish_future.result(TIMEOUT)
        puback_packet = publish_completion_data.puback
        self.assertIsInstance(puback_packet, mqtt5.PubackPacket)

        received_publish = callbacks.future_publish_received.result(TIMEOUT)
        self.assertIsInstance(received_publish, mqtt5.PublishPacket)
        self.assertEqual(received_publish.payload, payload)

        topic_filters = []
        topic_filters.append(topic_filter)
        unsubscribe_packet = mqtt5.UnsubscribePacket(topic_filters=topic_filters)
        unsubscribe_future = client.unsubscribe(unsubscribe_packet)
        unsuback_packet = unsubscribe_future.result(TIMEOUT)
        self.assertIsInstance(unsuback_packet, mqtt5.UnsubackPacket)

        publish_future = client.publish(publish_packet=publish_packet)
        publish_completion_data = publish_future.result(TIMEOUT)
        puback_packet = publish_completion_data.puback
        self.assertIsInstance(puback_packet, mqtt5.PubackPacket)

        self.assertEqual(callbacks.on_publish_received_counter, 1)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def do_correlation_data_test(self, outbound_correlation_data_bytes, outbound_correlation_data,
                                 expected_correlation_data_bytes, expected_correlation_data):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id
        payload = bytearray(os.urandom(256))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = client.subscribe(subscribe_packet=subscribe_packet)
        suback_packet = subscribe_future.result(TIMEOUT)
        self.assertIsInstance(suback_packet, mqtt5.SubackPacket)

        publish_packet = mqtt5.PublishPacket(
            payload=payload,
            topic=topic_filter,
            qos=mqtt5.QoS.AT_LEAST_ONCE,
            correlation_data_bytes=outbound_correlation_data_bytes,
            correlation_data=outbound_correlation_data)

        publish_future = client.publish(publish_packet=publish_packet)
        publish_completion_data = publish_future.result(TIMEOUT)
        puback_packet = publish_completion_data.puback
        self.assertIsInstance(puback_packet, mqtt5.PubackPacket)

        received_publish = callbacks.future_publish_received.result(TIMEOUT)
        self.assertIsInstance(received_publish, mqtt5.PublishPacket)
        self.assertEqual(received_publish.payload, payload)
        self.assertEqual(received_publish.correlation_data_bytes, expected_correlation_data_bytes)
        self.assertEqual(received_publish.correlation_data, expected_correlation_data)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_operation_publish_correlation_data_bytes_binary(self):
        correlation_data = bytearray(os.urandom(64))
        self.do_correlation_data_test(correlation_data, None, correlation_data, None)

    def test_operation_publish_correlation_data_bytes_string(self):
        correlation_data = "CorrelationData"
        correlation_data_as_bytes = correlation_data.encode('utf-8')
        self.do_correlation_data_test(correlation_data, None, correlation_data_as_bytes, correlation_data)

    def test_operation_publish_correlation_data_binary(self):
        correlation_data = bytearray(os.urandom(64))
        self.do_correlation_data_test(None, correlation_data, correlation_data, None)

    def test_operation_publish_correlation_data_string(self):
        correlation_data = "CorrelationData"
        correlation_data_as_bytes = correlation_data.encode('utf-8')
        self.do_correlation_data_test(None, correlation_data, correlation_data_as_bytes, correlation_data)

    def test_operation_publish_correlation_data_bytes_binary_precedence(self):
        correlation_data = bytearray(os.urandom(64))
        self.do_correlation_data_test(correlation_data, "Ignored", correlation_data, None)

    # ==============================================================
    #             OPERATION ERROR TEST CASES
    # ==============================================================

    def test_operation_error_null_publish(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        with self.assertRaises(Exception) as cm:
            client.publish(None)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_operation_error_null_subscribe(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        with self.assertRaises(Exception) as cm:
            client.subscribe(None)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_operation_error_null_unsubscribe(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        with self.assertRaises(Exception) as cm:
            client.unsubscribe(None)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def test_operation_rejoin_always(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id = create_client_id()

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883,
            session_behavior=mqtt5.ClientSessionBehaviorType.REJOIN_ALWAYS
        )
        client_options.connect_options = mqtt5.ConnectPacket(
            client_id=client_id, session_expiry_interval_sec=3600, keep_alive_interval_sec=360)
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks1 = Mqtt5TestCallbacks()
        client1 = self._create_client(client_options=client_options, callbacks=callbacks1)
        client1.start()
        callbacks1.future_connection_success.result(TIMEOUT)
        client1.stop()
        callbacks1.future_stopped.result(TIMEOUT)

        callbacks2 = Mqtt5TestCallbacks()
        client2 = self._create_client(client_options=client_options, callbacks=callbacks2)
        client2.start()
        connection_success_data = callbacks2.future_connection_success.result(TIMEOUT)
        connack_packet = connection_success_data.connack_packet
        self.assertTrue(connack_packet.session_present)
        client2.stop()
        callbacks2.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             QOS1 TEST CASES
    # ==============================================================

    def test_qos1_happy_path(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id_publisher = create_client_id()
        payload = "HELLO WORLD"
        topic_filter = "test/MQTT5_Binding_Python_" + client_id_publisher

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks1 = Mqtt5TestCallbacks()
        client1 = self._create_client(client_options=client_options, callbacks=callbacks1)
        client1.start()
        callbacks1.future_connection_success.result(TIMEOUT)

        client_options2 = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options2.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options2.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks2 = Mqtt5TestCallbacks()
        client2 = self._create_client(client_options=client_options2, callbacks=callbacks2)
        client2.start()
        callbacks2.future_connection_success.result(TIMEOUT)
        callbacks2.on_publish_receive_expected = 10

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = client2.subscribe(subscribe_packet=subscribe_packet)
        suback_packet = subscribe_future.result(TIMEOUT)
        self.assertIsInstance(suback_packet, mqtt5.SubackPacket)

        publishes = 10

        publish_packet = mqtt5.PublishPacket(
            payload=payload,
            topic=topic_filter,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        for x in range(publishes):
            publish_future = client1.publish(publish_packet)
            publish_future.result(TIMEOUT)

        client1.stop()
        callbacks1.future_stopped.result(TIMEOUT)

        callbacks2.future_expected_publishes_received.result(TIMEOUT)
        self.assertEqual(callbacks2.on_publish_received_counter, publishes)

        client2.stop()
        callbacks2.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             RETAIN TEST CASES
    # ==============================================================

    def test_retain_set_and_clear(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id_publisher = create_client_id()
        payload = "HELLO WORLD"
        topic_filter = "test/MQTT5_Binding_Python_" + client_id_publisher

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks1 = Mqtt5TestCallbacks()
        client1 = self._create_client(client_options=client_options, callbacks=callbacks1)
        client1.start()
        callbacks1.future_connection_success.result(TIMEOUT)

        publish_packet = mqtt5.PublishPacket(
            payload=payload,
            topic=topic_filter,
            retain=True,
            qos=mqtt5.QoS.AT_LEAST_ONCE)
        puback_future1 = client1.publish(publish_packet)
        puback_future1.result(TIMEOUT)

        client_options2 = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options2.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options2.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks2 = Mqtt5TestCallbacks()
        client2 = self._create_client(client_options=client_options2, callbacks=callbacks2)
        client2.start()
        callbacks2.future_connection_success.result(TIMEOUT)

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future1 = client2.subscribe(subscribe_packet=subscribe_packet)
        suback_packet1 = subscribe_future1.result(TIMEOUT)
        self.assertIsInstance(suback_packet1, mqtt5.SubackPacket)

        received_retained_publish1 = callbacks2.future_publish_received.result(TIMEOUT)
        self.assertIsInstance(received_retained_publish1, mqtt5.PublishPacket)
        client2.stop()
        callbacks2.future_stopped.result(TIMEOUT)

        publish_packet.payload = None
        puback_future2 = client1.publish(publish_packet)
        puback_future2.result(TIMEOUT)

        client1.stop()
        callbacks1.future_stopped.result(TIMEOUT)

        client_options3 = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options3.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options3.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks3 = Mqtt5TestCallbacks()
        client3 = self._create_client(client_options=client_options3, callbacks=callbacks3)
        client3.start()
        callbacks3.future_connection_success.result(TIMEOUT)

        subscribe_future2 = client3.subscribe(subscribe_packet=subscribe_packet)
        suback_packet2 = subscribe_future2.result(TIMEOUT)
        self.assertIsInstance(suback_packet2, mqtt5.SubackPacket)

        time.sleep(1)
        self.assertEqual(callbacks3.on_publish_received_counter, 0)

        client3.stop()
        callbacks3.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             INTERRUPTION TEST CASES
    # ==============================================================

    def test_interruption_sub(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        subscriptions = []
        subscriptions.append(mqtt5.Subscription(topic_filter=topic_filter, qos=mqtt5.QoS.AT_LEAST_ONCE))
        subscribe_packet = mqtt5.SubscribePacket(
            subscriptions=subscriptions)
        subscribe_future = client.subscribe(subscribe_packet=subscribe_packet)
        client.stop()

        with self.assertRaises(Exception):
            subscribe_future.result(TIMEOUT)

        callbacks.future_stopped.result(TIMEOUT)

    def test_interruption_unsub(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        topic_filters = []
        topic_filters.append(topic_filter)
        unsubscribe_packet = mqtt5.UnsubscribePacket(topic_filters=topic_filters)
        unsubscribe_future = client.unsubscribe(unsubscribe_packet)
        client.stop()

        with self.assertRaises(Exception):
            unsubscribe_future.result(TIMEOUT)

        callbacks.future_stopped.result(TIMEOUT)

    def test_interruption_qos1_publish(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id = create_client_id()
        topic_filter = "test/MQTT5_Binding_Python_" + client_id
        payload = "test payload"

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        publish_packet = mqtt5.PublishPacket(
            payload=payload,
            topic=topic_filter,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        publish_future = client.publish(publish_packet=publish_packet)
        client.stop()

        with self.assertRaises(Exception):
            publish_future.result(TIMEOUT)

        callbacks.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             MISC TEST CASES
    # ==============================================================

    def test_operation_statistics_uc1(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_id_publisher = create_client_id()
        payload = "HELLO WORLD"
        topic_filter = "test/MQTT5_Binding_Python_" + client_id_publisher

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )
        client_options.connect_options = mqtt5.ConnectPacket(client_id=create_client_id())
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)

        # Make sure the operation statistics are empty
        statistics = client.get_stats()
        self.assertEqual(statistics.incomplete_operation_count, 0)
        self.assertEqual(statistics.incomplete_operation_size, 0)
        self.assertEqual(statistics.unacked_operation_count, 0)
        self.assertEqual(statistics.unacked_operation_size, 0)

        publish_packet = mqtt5.PublishPacket(
            payload=payload,
            topic=topic_filter,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        publishes = 10
        for x in range(publishes):
            publish_future = client.publish(publish_packet)
            publish_future.result(TIMEOUT)

        # Make sure the operation statistics are empty
        statistics = client.get_stats()
        self.assertEqual(statistics.incomplete_operation_count, 0)
        self.assertEqual(statistics.incomplete_operation_size, 0)
        self.assertEqual(statistics.unacked_operation_count, 0)
        self.assertEqual(statistics.unacked_operation_size, 0)

        client.stop()
        callbacks.future_stopped.result(TIMEOUT)


if __name__ == 'main':
    unittest.main()
