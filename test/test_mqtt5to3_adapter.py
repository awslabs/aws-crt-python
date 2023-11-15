# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from concurrent.futures import Future
from awscrt import mqtt5, io, http, exceptions
from awscrt.mqtt import Connection, ConnectReturnCode, OnConnectionSuccessData, OnConnectionFailureData, OnConnectionClosedData, QoS
from test import NativeResourceTest
from test.test_mqtt5 import Mqtt5TestCallbacks, _get_env_variable, create_client_id
import unittest
import uuid


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


class Mqtt311TestCallbacks():
    def __init__(self):
        self.last_exception = None

        self.future_connection_success = Future()
        self.future_connection_failure = Future()
        self.future_resumed = Future()
        self.future_interrupted = Future()
        self.future_closed = Future()
        self.future_message_received = Future()
        self.received_message = 0

    def on_connection_interrupted(self, connection: Connection, error: exceptions.AwsCrtError):
        if self.future_interrupted:
            self.future_interrupted.set_result(error)
            self.future_connection_success = self._reset_future(self.future_connection_success)

    def on_connection_resumed(self, connection: Connection, return_code: ConnectReturnCode, session_present: bool):
        if self.future_resumed:
            self.future_resumed.set_result({'return_code': return_code, "session_present": session_present})

    def on_connection_success(self, connection: Connection, callback_data: OnConnectionSuccessData):
        if self.future_connection_success:
            self.future_connection_success.set_result(
                {'return_code': callback_data.return_code, "session_present": callback_data.session_present})

    def on_connection_failure(self, connection: Connection, callback_data: OnConnectionFailureData):
        if self.future_connection_failure:
            self.future_connection_failure.set_result({'error': callback_data.error})

    def on_connection_closed(self, connection: Connection, callback_data: OnConnectionClosedData):
        if self.future_closed:
            self.future_closed.set_result({})

    def on_message(self, **kwargs):
        self.received_message += 1
        if self.future_message_received:
            self.future_message_received.set_result(kwargs)

    def _reset_future(self, future: Future):
        if future.done():
            return Future()
        return future


class Mqtt5to3AdapterTest(NativeResourceTest):
    TEST_MSG = 'NOTICE ME!'.encode('utf8')

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

    def _create_connection(self,
                           client: mqtt5.Client,
                           mqtt3_callbacks: Mqtt311TestCallbacks = None):
        connection = client.new_connection(on_connection_closed=mqtt3_callbacks.on_connection_closed,
                                           on_connection_failure=mqtt3_callbacks.on_connection_failure,
                                           on_connection_success=mqtt3_callbacks.on_connection_success,
                                           on_connection_resumed=mqtt3_callbacks.on_connection_resumed,
                                           on_connection_interrupted=mqtt3_callbacks.on_connection_interrupted,)
        return connection

    # # ==============================================================
    # #             MQTT5 CLIENT SETUP
    # # ==============================================================

    def _setup_direct_connect_minimum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        callbacks = Mqtt5TestCallbacks()
        return self._create_client(client_options=client_options, callbacks=callbacks), callbacks

    def _setup_direct_connect_basic_auth(self):
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
        return self._create_client(client_options=client_options, callbacks=callbacks), callbacks

    def _setup_direct_connect_mutual_tls(self):
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
        return self._create_client(client_options=client_options, callbacks=callbacks), callbacks

    # ==============================================================
    #             WEBSOCKET CONNECT TEST SETUP
    # ==============================================================

    def _setup_websocket_connect_minimum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_WS_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_WS_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        callbacks = Mqtt5TestCallbacks()
        client_options.websocket_handshake_transform = callbacks.ws_handshake_transform

        return self._create_client(client_options=client_options, callbacks=callbacks), callbacks

    def _setup_websocket_connect_http_proxy_tls(self):
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

        return self._create_client(client_options=client_options, callbacks=callbacks), callbacks

    def _test_with_mqtt3_connect(self, setup_client: callable):
        client, callbacks = setup_client()
        connection = client.new_connection()
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def _test_with_mqtt5_connect(self, setup_client: callable):
        client, callbacks = setup_client()
        connection = client.new_connection()
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             CONNECTION TEST HELPER FUNCTIONS
    # ==============================================================

    def _test_with_mqtt3_connect(self, setup_client: callable):
        client, callbacks = setup_client()
        connection = client.new_connection()
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def _test_with_mqtt5_connect(self, setup_client: callable):
        client, callbacks = setup_client()
        connection = client.new_connection()
        client.start()
        callbacks.future_connection_success.result(TIMEOUT)
        client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    # ==============================================================
    #             CREATION TEST CASES
    # ==============================================================

    def test_client_creation_minimum(self):
        client = self._create_client()
        connection = client.new_connection()

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
            client_id=create_client_id(),
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
        connection = client.new_connection()

    # ==============================================================
    #         CONNECT THROUGH MQTT311 INTERFACE TEST CASES
    # ==============================================================
    def test_direct_connect_through_mqtt311_minimum(self):
        self._test_with_mqtt3_connect(self._setup_direct_connect_minimum)

    # def test_direct_connect_through_mqtt311_basic_auth(self):
    #     self._test_with_mqtt3_connect(self._setup_direct_connect_basic_auth)

    def test_direct_connect_through_mqtt311_mutual_tls(self):
        self._test_with_mqtt3_connect(self._setup_direct_connect_mutual_tls)

    # def test_direct_connect_through_mqtt311_websocket_minimum(self):
    #     self._test_with_mqtt3_connect(self._setup_websocket_connect_minimum)

    # def test_direct_connect_through_mqtt311_websocket_http_proxy_tls(self):
    #     self._test_with_mqtt3_connect(self._setup_websocket_connect_http_proxy_tls)

    # ==============================================================
    #         CONNECT THROUGH MQTT5 INTERFACE TEST CASES
    # ==============================================================

    def test_direct_connect_through_mqtt5_minimum(self):
        self._test_with_mqtt5_connect(self._setup_direct_connect_minimum)

    # def test_direct_connect_through_mqtt5_basic_auth(self):
    #     self._test_with_mqtt5_connect(self._setup_direct_connect_basic_auth)

    def test_direct_connect_through_mqtt5_mutual_tls(self):
        self._test_with_mqtt5_connect(self._setup_direct_connect_mutual_tls)

    # def test_direct_connect_through_mqtt5_websocket_minimum(self):
    #     self._test_with_mqtt5_connect(self._setup_websocket_connect_minimum)

    # def test_direct_connect_through_mqtt5_websocket_http_proxy_tls(self):
    #     self._test_with_mqtt5_connect(self._setup_websocket_connect_http_proxy_tls)

    # ==============================================================
    #             OPERATION TEST CASES
    # ==============================================================

    def test_operation_sub_unsub(self):
        TEST_TOPIC = '/test/topic/adapter' + str(uuid.uuid4())

        client, mqtt5_callbacks = self._setup_direct_connect_mutual_tls()
        mqtt311_callbacks = Mqtt311TestCallbacks()
        connection = self._create_connection(client, mqtt311_callbacks)

        connection.connect().result(TIMEOUT)

        # subscribe
        subscribed, packet_id = connection.subscribe(TEST_TOPIC, QoS.AT_LEAST_ONCE, mqtt311_callbacks.on_message)
        suback = subscribed.result(TIMEOUT)
        self.assertEqual(packet_id, suback['packet_id'])
        self.assertEqual(TEST_TOPIC, suback['topic'])
        self.assertIs(QoS.AT_LEAST_ONCE, suback['qos'])

        # publish
        published, packet_id = connection.publish(TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(TIMEOUT)
        self.assertEqual(packet_id, puback['packet_id'])

        # receive message
        rcv = mqtt311_callbacks.future_message_received.result(TIMEOUT)
        self.assertEqual(TEST_TOPIC, rcv['topic'])
        self.assertEqual(self.TEST_MSG, rcv['payload'])
        self.assertFalse(rcv['dup'])
        self.assertEqual(QoS.AT_LEAST_ONCE, rcv['qos'])
        self.assertFalse(rcv['retain'])

        # unsubscribe
        unsubscribed, packet_id = connection.unsubscribe(TEST_TOPIC)
        unsuback = unsubscribed.result(TIMEOUT)
        self.assertEqual(packet_id, unsuback['packet_id'])

        # publish
        published, packet_id = connection.publish(TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(TIMEOUT)
        self.assertEqual(packet_id, puback['packet_id'])

        self.assertEqual(mqtt311_callbacks.received_message, 1)
        self.assertEqual(mqtt5_callbacks.on_publish_received_counter, 1)

        connection.disconnect().result(TIMEOUT)

    def test_operation_null_ack(self):
        TEST_TOPIC = '/test/topic/adapter' + str(uuid.uuid4())
        exception_occurred = False

        client, mqtt5_callbacks = self._setup_direct_connect_mutual_tls()
        mqtt311_callbacks = Mqtt311TestCallbacks()
        connection = self._create_connection(client, mqtt311_callbacks)

        # publish an offline packet so that the publish operation would be incomplete
        published, packet_id = connection.publish(TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)

        # Manually destroyed the connection so that the incomplete publish operation should fail with exception
        del connection
        try:
            published.result(TIMEOUT)
        except TimeoutError:
            # Directly failed the test if the result time out
            self.assertTrue(False, "Operation Time out. The connection does not fail the callback on destroy. ")
        except Exception:
            exception_occurred = True

        assert (exception_occurred)

    # ==============================================================
    #                 MQTT311 CALLBACK TEST CASES
    # ==============================================================
    def test_connection_success_callback(self):
        client, _ = self._setup_direct_connect_minimum()
        mqtt311_callbacks = Mqtt311TestCallbacks()
        connection = self._create_connection(client, mqtt311_callbacks)

        connection.connect().result(TIMEOUT)
        mqtt311_callbacks.future_connection_success.result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_connection_failure_callback(self):
        client_options = mqtt5.ClientOptions(
            host_name="badhost",
            port=1883
        )
        callbacks = Mqtt5TestCallbacks()
        client = self._create_client(client_options=client_options, callbacks=callbacks)
        mqtt311_callbacks = Mqtt311TestCallbacks()
        connection = self._create_connection(client, mqtt311_callbacks)

        try:
            connection.connect().result(TIMEOUT)
        except Exception:
            exception_occurred = True
        self.assertTrue(exception_occurred, "Exception did not occur when connecting with invalid arguments!")

        failure_data = mqtt311_callbacks.future_connection_failure.result(TIMEOUT)
        self.assertTrue(failure_data['error'] is not None)

    def test_connection_interrupted_and_resumed_callback(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT5_DIRECT_MQTT_PORT"))

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=input_port
        )
        client_options.connect_options = mqtt5.ConnectPacket()
        client_options.connect_options.client_id = create_client_id()

        client1 = self._create_client(client_options=client_options)
        client2 = self._create_client(client_options=client_options)

        mqtt311_callbacks1 = Mqtt311TestCallbacks()
        mqtt311_callbacks2 = Mqtt311TestCallbacks()

        # Create two connection with the same client id
        connection1 = self._create_connection(client1, mqtt311_callbacks1)
        connection2 = self._create_connection(client2, mqtt311_callbacks2)

        connection1.connect().result(TIMEOUT)

        connection2.connect().result(TIMEOUT)

        # with connection2 connected, connection1 should be interrupted
        mqtt311_callbacks1.future_interrupted.result(TIMEOUT)
        # The connection1 should automatically re-connected
        mqtt311_callbacks1.future_resumed.result(TIMEOUT)

        # At this point, connection2 should be interrupted
        mqtt311_callbacks2.future_interrupted.result(TIMEOUT)

        connection1.disconnect().result(TIMEOUT)
        connection2.disconnect().result(TIMEOUT)

    # ==============================================================
    #                 ADAPTER TEST CASES
    # ==============================================================
    def test_multiple_adapters(self):
        TEST_TOPIC1 = '/test/topic/adapter1' + str(uuid.uuid4())
        TEST_TOPIC2 = '/test/topic/adapter2' + str(uuid.uuid4())
        TEST_TOPIC3 = '/test/topic/adapter3' + str(uuid.uuid4())

        client, mqtt5_callbacks = self._setup_direct_connect_mutual_tls()
        mqtt311_callbacks1 = Mqtt311TestCallbacks()
        connection1 = self._create_connection(client, mqtt3_callbacks=mqtt311_callbacks1)
        mqtt311_callbacks2 = Mqtt311TestCallbacks()
        connection2 = self._create_connection(client, mqtt3_callbacks=mqtt311_callbacks2)
        mqtt311_callbacks3 = Mqtt311TestCallbacks()
        connection3 = self._create_connection(client, mqtt3_callbacks=mqtt311_callbacks3)

        client.start()
        mqtt5_callbacks.future_connection_success.result(TIMEOUT)

        # subscribe
        subscribed, packet_id = connection1.subscribe(
            TEST_TOPIC1, QoS.AT_LEAST_ONCE, mqtt311_callbacks1.on_message)
        suback = subscribed.result(TIMEOUT)
        subscribed, packet_id = connection2.subscribe(
            TEST_TOPIC2, QoS.AT_LEAST_ONCE, mqtt311_callbacks2.on_message)
        suback = subscribed.result(TIMEOUT)
        subscribed, packet_id = connection3.subscribe(
            TEST_TOPIC3, QoS.AT_LEAST_ONCE, mqtt311_callbacks3.on_message)
        suback = subscribed.result(TIMEOUT)

        # publish on topic1
        publish_packet = mqtt5.PublishPacket(
            payload=self.TEST_MSG,
            topic=TEST_TOPIC1,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        client.publish(publish_packet=publish_packet).result(TIMEOUT)

        # only connection1 should receive message
        mqtt311_callbacks1.future_message_received.result(TIMEOUT)

        self.assertEqual(mqtt311_callbacks1.received_message, 1)
        self.assertEqual(mqtt311_callbacks2.received_message, 0)
        self.assertEqual(mqtt311_callbacks3.received_message, 0)

        # publish on topic2
        publish_packet = mqtt5.PublishPacket(
            payload=self.TEST_MSG,
            topic=TEST_TOPIC2,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        client.publish(publish_packet=publish_packet).result(TIMEOUT)

        # connection2 should receive message
        mqtt311_callbacks2.future_message_received.result(TIMEOUT)

        self.assertEqual(mqtt311_callbacks1.received_message, 1)
        self.assertEqual(mqtt311_callbacks2.received_message, 1)
        self.assertEqual(mqtt311_callbacks3.received_message, 0)

        # publish on topic3
        publish_packet = mqtt5.PublishPacket(
            payload=self.TEST_MSG,
            topic=TEST_TOPIC3,
            qos=mqtt5.QoS.AT_LEAST_ONCE)

        client.publish(publish_packet=publish_packet).result(TIMEOUT)

        # connection3 should receive message
        mqtt311_callbacks3.future_message_received.result(TIMEOUT)
        self.assertEqual(mqtt311_callbacks1.received_message, 1)
        self.assertEqual(mqtt311_callbacks2.received_message, 1)
        self.assertEqual(mqtt311_callbacks3.received_message, 1)

        client.stop()
        mqtt5_callbacks.future_stopped.result(TIMEOUT)


if __name__ == 'main':
    unittest.main()
