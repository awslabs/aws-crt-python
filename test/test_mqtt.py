# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, Pkcs11Lib, TlsContextOptions
from awscrt import http
from awscrt.mqtt import Client, Connection, QoS, Will, OnConnectionClosedData, OnConnectionFailureData, OnConnectionSuccessData, ConnectReturnCode
from test import NativeResourceTest
from concurrent.futures import Future
import os
import unittest
import uuid
import time

TIMEOUT = 100.0


def _get_env_variable(env_name):
    env_data = os.environ.get(env_name)
    if not env_data:
        raise unittest.SkipTest(f"test requires env var: {env_name}")
    return env_data


def create_client_id():
    return 'aws-crt-python-unit-test-{0}'.format(uuid.uuid4())


class MqttConnectionTest(NativeResourceTest):
    TEST_TOPIC = '/test/me/senpai/' + str(uuid.uuid4())
    TEST_MSG = 'NOTICE ME!'.encode('utf8')

    def _create_connection(
            self,
            endpoint,
            tls_context,
            port=8883,
            use_static_singletons=False,
            client_id=None,
            on_connection_success_callback=None,
            on_connection_failure_callback=None,
            on_connection_closed_callback=None,
            on_connection_resumed_callback=None):
        if use_static_singletons:
            client = Client(tls_ctx=tls_context)
        else:
            elg = EventLoopGroup()
            resolver = DefaultHostResolver(elg)
            bootstrap = ClientBootstrap(elg, resolver)
            client = Client(bootstrap, tls_context)

        connection = Connection(
            client=client,
            client_id=client_id if client_id else create_client_id(),
            host_name=endpoint,
            port=port,
            on_connection_closed=on_connection_closed_callback,
            on_connection_failure=on_connection_failure_callback,
            on_connection_success=on_connection_success_callback,
            on_connection_resumed=on_connection_resumed_callback)
        return connection

    def test_connect_disconnect(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")

        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)

        connection = self._create_connection(test_input_endpoint, test_tls)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_ecc_connect_disconnect(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_ECC_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_ECC_KEY")

        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)

        connection = self._create_connection(test_input_endpoint, test_tls)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_pkcs11(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_pkcs11_lib = _get_env_variable("AWS_TEST_PKCS11_LIB")
        test_input_pkcs11_pin = _get_env_variable("AWS_TEST_PKCS11_PIN")
        test_input_pkcs11_token_label = _get_env_variable("AWS_TEST_PKCS11_TOKEN_LABEL")
        test_input_pkcs11_private_key = _get_env_variable("AWS_TEST_PKCS11_PKEY_LABEL")
        test_input_pkcs11_cert = _get_env_variable("AWS_TEST_PKCS11_CERT_FILE")

        test_pkcs11_lib = Pkcs11Lib(file=test_input_pkcs11_lib, behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)
        test_tls_opts = TlsContextOptions.create_client_with_mtls_pkcs11(
            pkcs11_lib=test_pkcs11_lib,
            user_pin=test_input_pkcs11_pin,
            token_label=test_input_pkcs11_token_label,
            private_key_label=test_input_pkcs11_private_key,
            cert_file_path=test_input_pkcs11_cert
        )
        test_tls = ClientTlsContext(test_tls_opts)

        connection = self._create_connection(test_input_endpoint, test_tls)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_pub_sub(self):
        self.TEST_TOPIC = '/test/me/senpai/' + str(uuid.uuid4())
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)
        connection = self._create_connection(test_input_endpoint, test_tls)

        connection.connect().result(TIMEOUT)
        received = Future()

        def on_message(**kwargs):
            received.set_result(kwargs)

        # subscribe
        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE, on_message)
        suback = subscribed.result(TIMEOUT)
        self.assertEqual(packet_id, suback['packet_id'])
        self.assertEqual(self.TEST_TOPIC, suback['topic'])
        self.assertIs(QoS.AT_LEAST_ONCE, suback['qos'])

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(TIMEOUT)
        self.assertEqual(packet_id, puback['packet_id'])

        # receive message
        rcv = received.result(TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv['topic'])
        self.assertEqual(self.TEST_MSG, rcv['payload'])
        self.assertFalse(rcv['dup'])
        self.assertEqual(QoS.AT_LEAST_ONCE, rcv['qos'])
        self.assertFalse(rcv['retain'])

        # unsubscribe
        unsubscribed, packet_id = connection.unsubscribe(self.TEST_TOPIC)
        unsuback = unsubscribed.result(TIMEOUT)
        self.assertEqual(packet_id, unsuback['packet_id'])

        # disconnect
        connection.disconnect().result(TIMEOUT)

    def test_will(self):
        self.TEST_TOPIC = '/test/me/senpai/' + str(uuid.uuid4())
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, test_tls)

        will_client_id = create_client_id()
        connection = Connection(
            client=client,
            client_id=will_client_id,
            host_name=test_input_endpoint,
            port=8883,
            will=Will(self.TEST_TOPIC, QoS.AT_LEAST_ONCE, self.TEST_MSG, False),
            ping_timeout_ms=10000,
            keep_alive_secs=30
        )
        connection.connect().result(TIMEOUT)

        subscriber = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=test_input_endpoint,
            port=8883,
            ping_timeout_ms=10000,
            keep_alive_secs=30
        )
        subscriber.connect().result(TIMEOUT)

        received = Future()

        def on_message(**kwargs):
            received.set_result(kwargs)

        # subscribe
        subscribed, packet_id = subscriber.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE, on_message)
        suback = subscribed.result(TIMEOUT)
        self.assertEqual(packet_id, suback['packet_id'])
        self.assertEqual(self.TEST_TOPIC, suback['topic'])
        self.assertIs(QoS.AT_LEAST_ONCE, suback['qos'])

        # wait a few seconds to ensure we can make another client ID connect (don't trigger IoT Core limit)
        time.sleep(2)

        # Disconnect the will client to send the will by making another connection with the same client id
        disconnecter = Connection(
            client=client,
            client_id=will_client_id,
            host_name=test_input_endpoint,
            port=8883,
            will=Will(self.TEST_TOPIC, QoS.AT_LEAST_ONCE, self.TEST_MSG, False),
            ping_timeout_ms=10000,
            keep_alive_secs=30
        )
        disconnecter.connect().result(TIMEOUT)

        # Receive message
        rcv = received.result(TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv['topic'])
        self.assertEqual(self.TEST_MSG, rcv['payload'])
        self.assertFalse(rcv['dup'])
        self.assertEqual(QoS.AT_LEAST_ONCE, rcv['qos'])
        self.assertFalse(rcv['retain'])

        # Disconnect the other clients
        connection.disconnect().result(TIMEOUT)
        disconnecter.disconnect().result(TIMEOUT)

        # unsubscribe
        unsubscribed, packet_id = subscriber.unsubscribe(self.TEST_TOPIC)
        unsuback = unsubscribed.result(TIMEOUT)
        self.assertEqual(packet_id, unsuback['packet_id'])

        # disconnect
        subscriber.disconnect().result(TIMEOUT)

    def test_on_message(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)
        connection = self._create_connection(test_input_endpoint, test_tls)

        received = Future()

        def on_message(**kwargs):
            received.set_result(kwargs)

        # on_message for connection has to be set before connect, or possible race will happen
        connection.on_message(on_message)

        connection.connect().result(TIMEOUT)
        # subscribe without callback
        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE)
        subscribed.result(TIMEOUT)

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(TIMEOUT)

        # receive message
        rcv = received.result(TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv['topic'])
        self.assertEqual(self.TEST_MSG, rcv['payload'])
        self.assertFalse(rcv['dup'])
        self.assertEqual(QoS.AT_LEAST_ONCE, rcv['qos'])
        self.assertFalse(rcv['retain'])

        # disconnect
        connection.disconnect().result(TIMEOUT)

    def test_on_message_old_fn_signature(self):
        # ensure that message-received callbacks with the old function signature still work

        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)
        connection = self._create_connection(test_input_endpoint, test_tls)

        any_received = Future()
        sub_received = Future()

        # Note: Testing degenerate callback signature that failed to take
        # forward-compatibility **kwargs.
        def on_any_message(topic, payload):
            any_received.set_result({'topic': topic, 'payload': payload})

        def on_sub_message(topic, payload):
            sub_received.set_result({'topic': topic, 'payload': payload})

        # on_message for connection has to be set before connect, or possible race will happen
        connection.on_message(on_any_message)

        connection.connect().result(TIMEOUT)
        # subscribe without callback
        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE, on_sub_message)
        subscribed.result(TIMEOUT)

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(TIMEOUT)

        # receive message
        rcv = any_received.result(TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv['topic'])
        self.assertEqual(self.TEST_MSG, rcv['payload'])

        rcv = sub_received.result(TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv['topic'])
        self.assertEqual(self.TEST_MSG, rcv['payload'])

        # disconnect
        connection.disconnect().result(TIMEOUT)

    def test_connect_disconnect_with_default_singletons(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")

        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)

        connection = self._create_connection(test_input_endpoint, test_tls, use_static_singletons=True)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

        # free singletons
        ClientBootstrap.release_static_default()
        EventLoopGroup.release_static_default()
        DefaultHostResolver.release_static_default()

    def test_connect_publish_wait_statistics_disconnect(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)
        connection = self._create_connection(test_input_endpoint, test_tls)

        connection.connect().result(TIMEOUT)

        # check operation statistics
        statistics = connection.get_stats()
        self.assertEqual(statistics.incomplete_operation_count, 0)
        self.assertEqual(statistics.incomplete_operation_size, 0)
        self.assertEqual(statistics.unacked_operation_count, 0)
        self.assertEqual(statistics.unacked_operation_size, 0)

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(TIMEOUT)
        self.assertEqual(packet_id, puback['packet_id'])

        # check operation statistics
        statistics = connection.get_stats()
        self.assertEqual(statistics.incomplete_operation_count, 0)
        self.assertEqual(statistics.incomplete_operation_size, 0)
        self.assertEqual(statistics.unacked_operation_count, 0)
        self.assertEqual(statistics.unacked_operation_size, 0)

        # disconnect
        connection.disconnect().result(TIMEOUT)

    def test_connect_publish_statistics_wait_disconnect(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)
        connection = self._create_connection(test_input_endpoint, test_tls)

        connection.connect().result(TIMEOUT)

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        # Per packet: (The size of the topic, the size of the payload, 2 for the header and 2 for the packet ID)
        expected_size = len(self.TEST_TOPIC) + len(self.TEST_MSG) + 4

        # check operation statistics
        statistics = connection.get_stats()
        self.assertEqual(statistics.incomplete_operation_count, 1)
        self.assertEqual(statistics.incomplete_operation_size, expected_size)
        # NOTE: Unacked MAY be zero because we have not invoked the future yet
        # and so it has not had time to move to the socket. With Python especially, it seems to heavily depend on how fast
        # the test is executed, which makes it sometimes rarely get into the unacked operation and then it is non-zero.
        # To fix this, we just make sure it is within expected bounds (0 or within packet size).
        self.assertTrue(statistics.unacked_operation_count <= 1)
        self.assertTrue(statistics.unacked_operation_count <= expected_size)

        # wait for PubAck
        puback = published.result(TIMEOUT)
        self.assertEqual(packet_id, puback['packet_id'])

        # check operation statistics
        statistics = connection.get_stats()
        self.assertEqual(statistics.incomplete_operation_count, 0)
        self.assertEqual(statistics.incomplete_operation_size, 0)
        self.assertEqual(statistics.unacked_operation_count, 0)
        self.assertEqual(statistics.unacked_operation_size, 0)

        # disconnect
        connection.disconnect().result(TIMEOUT)

    def test_connect_disconnect_with_callbacks_happy(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)

        on_connection_success_future = Future()
        on_connection_closed_future = Future()

        def on_connection_success_callback(connection, callback_data: OnConnectionSuccessData):
            on_connection_success_future.set_result(
                {'return_code': callback_data.return_code, "session_present": callback_data.session_present})

        def on_connection_failure_callback(connection, callback_data: OnConnectionFailureData):
            pass

        def on_connection_closed_callback(connection, callback_data: OnConnectionClosedData):
            on_connection_closed_future.set_result({})

        connection = self._create_connection(
            endpoint=test_input_endpoint,
            tls_context=test_tls,
            on_connection_success_callback=on_connection_success_callback,
            on_connection_failure_callback=on_connection_failure_callback,
            on_connection_closed_callback=on_connection_closed_callback)
        connection.connect().result(TIMEOUT)
        success_data = on_connection_success_future.result(TIMEOUT)
        self.assertEqual(success_data['return_code'], ConnectReturnCode.ACCEPTED)
        self.assertEqual(success_data['session_present'], False)
        connection.disconnect().result(TIMEOUT)
        on_connection_closed_future.result(TIMEOUT)

    def test_connect_disconnect_with_callbacks_unhappy(self):
        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)

        on_onnection_failure_future = Future()

        def on_connection_success_callback(connection, callback_data: OnConnectionSuccessData):
            pass

        def on_connection_failure_callback(connection, callback_data: OnConnectionFailureData):
            on_onnection_failure_future.set_result({'error': callback_data.error})

        def on_connection_closed_callback(connection, callback_data: OnConnectionClosedData):
            pass

        connection = self._create_connection(
            endpoint=test_input_endpoint,
            tls_context=test_tls,
            port=1234,
            on_connection_success_callback=on_connection_success_callback,
            on_connection_failure_callback=on_connection_failure_callback,
            on_connection_closed_callback=on_connection_closed_callback)

        exception_occurred = False
        try:
            connection.connect().result(TIMEOUT)
        except Exception:
            exception_occurred = True
        self.assertTrue(exception_occurred, "Exception did not occur when connecting with invalid arguments!")

        failure_data = on_onnection_failure_future.result(TIMEOUT)
        self.assertTrue(failure_data['error'] is not None)

    def test_connect_disconnect_with_callbacks_happy_on_resume(self):
        # Check that an on_connection_success callback fires on a resumed connection.

        # NOTE Since there is no mocked server available on this abstraction level, the only sensible approach
        # is to interrupt a connection, and wait for it to be resumed automatically. For that, another client
        # with the same client_id connects to the server and then immediately disconnects.

        test_input_endpoint = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")
        test_input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        test_input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        test_tls_opts = TlsContextOptions.create_client_with_mtls_from_path(test_input_cert, test_input_key)
        test_tls = ClientTlsContext(test_tls_opts)

        on_connection_success_future = Future()
        on_connection_closed_future = Future()
        on_connection_resumed_future = Future()

        def on_connection_success_callback(connection, callback_data: OnConnectionSuccessData):
            on_connection_success_future.set_result(
                {'return_code': callback_data.return_code, "session_present": callback_data.session_present})

        def on_connection_closed_callback(connection, callback_data: OnConnectionClosedData):
            on_connection_closed_future.set_result({})

        def on_connection_resumed_callback(connection, return_code: ConnectReturnCode, session_present):
            on_connection_resumed_future.set_result(
                {'return_code': return_code, "session_present": session_present})

        connection = self._create_connection(
            endpoint=test_input_endpoint,
            tls_context=test_tls,
            on_connection_success_callback=on_connection_success_callback,
            on_connection_closed_callback=on_connection_closed_callback,
            on_connection_resumed_callback=on_connection_resumed_callback)
        connection.connect().result(TIMEOUT)
        success_data = on_connection_success_future.result(TIMEOUT)
        self.assertEqual(success_data['return_code'], ConnectReturnCode.ACCEPTED)
        self.assertEqual(success_data['session_present'], False)

        # Reset the future for the reconnect attempt.
        on_connection_success_future = Future()

        on_connection_success_future_dup = Future()

        def on_connection_success_callback_dup(connection, callback_data: OnConnectionSuccessData):
            on_connection_success_future_dup.set_result({})

        # Reuse the same client_id to displace the first client.
        connection_dup = self._create_connection(
            endpoint=test_input_endpoint,
            tls_context=test_tls,
            client_id=connection.client_id,
            on_connection_success_callback=on_connection_success_callback_dup)

        connection_dup.connect().result(TIMEOUT)
        on_connection_success_future_dup.result(TIMEOUT)
        connection_dup.disconnect().result(TIMEOUT)

        # After the second client disconnects, the first one should reconnect,
        # and on_connection_success callback should be fired once again.
        on_connection_resumed_future.result(TIMEOUT)
        success_data = on_connection_success_future.result(TIMEOUT)

        self.assertEqual(success_data['return_code'], ConnectReturnCode.ACCEPTED)
        self.assertEqual(success_data['session_present'], False)

        connection.disconnect().result(TIMEOUT)
        on_connection_closed_future.result(TIMEOUT)

    # ==============================================================
    #             MOSQUITTO CONNECTION TESTS
    # ==============================================================

    def test_mqtt311_direct_connect_minimum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_PORT"))

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, None)
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_direct_connect_basic_auth(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_BASIC_AUTH_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_BASIC_AUTH_PORT"))
        input_username = _get_env_variable("AWS_TEST_MQTT311_BASIC_AUTH_USERNAME")
        input_password = _get_env_variable("AWS_TEST_MQTT311_BASIC_AUTH_PASSWORD")

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, None)
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port,
            username=input_username,
            password=input_password)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_direct_connect_tls(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_TLS_PORT"))

        tls_ctx_options = TlsContextOptions()
        tls_ctx_options.verify_peer = False
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_direct_connect_mutual_tls(self):
        input_cert = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_RSA_KEY")
        input_host = _get_env_variable("AWS_TEST_MQTT311_IOT_CORE_HOST")

        tls_ctx_options = TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host,
            port=8883)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_direct_connect_http_proxy_tls(self):
        input_proxy_host = _get_env_variable("AWS_TEST_MQTT311_PROXY_HOST")
        input_proxy_port = int(_get_env_variable("AWS_TEST_MQTT311_PROXY_PORT"))
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_DIRECT_MQTT_TLS_PORT"))

        tls_ctx_options = TlsContextOptions()
        tls_ctx_options.verify_peer = False
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))

        http_proxy_options = http.HttpProxyOptions(
            host_name=input_proxy_host,
            port=input_proxy_port
        )
        http_proxy_options.connection_type = http.HttpProxyConnectionType.Tunneling
        http_proxy_options.auth_type = http.HttpProxyAuthenticationType.Nothing

        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port,
            proxy_options=http_proxy_options)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_websocket_connect_minimum(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_WS_MQTT_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_WS_MQTT_PORT"))

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        def sign_function(transform_args, **kwargs):
            transform_args.set_done()

        client = Client(bootstrap, None)
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port,
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_websocket_connect_basic_auth(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_WS_MQTT_BASIC_AUTH_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_WS_MQTT_BASIC_AUTH_PORT"))
        input_username = _get_env_variable("AWS_TEST_MQTT311_BASIC_AUTH_USERNAME")
        input_password = _get_env_variable("AWS_TEST_MQTT311_BASIC_AUTH_PASSWORD")

        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        def sign_function(transform_args, **kwargs):
            transform_args.set_done()

        client = Client(bootstrap, None)
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port,
            username=input_username,
            password=input_password,
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_websocket_connect_tls(self):
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_WS_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_WS_MQTT_TLS_PORT"))

        tls_ctx_options = TlsContextOptions()
        tls_ctx_options.verify_peer = False
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        def sign_function(transform_args, **kwargs):
            transform_args.set_done()

        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port,
            use_websockets=True,
            websocket_handshake_transform=sign_function)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mqtt311_websocket_connect_http_proxy_tls(self):
        input_proxy_host = _get_env_variable("AWS_TEST_MQTT311_PROXY_HOST")
        input_proxy_port = int(_get_env_variable("AWS_TEST_MQTT311_PROXY_PORT"))
        input_host_name = _get_env_variable("AWS_TEST_MQTT311_WS_MQTT_TLS_HOST")
        input_port = int(_get_env_variable("AWS_TEST_MQTT311_WS_MQTT_TLS_PORT"))

        tls_ctx_options = TlsContextOptions()
        tls_ctx_options.verify_peer = False
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        http_proxy_options = http.HttpProxyOptions(
            host_name=input_proxy_host,
            port=input_proxy_port
        )
        http_proxy_options.connection_type = http.HttpProxyConnectionType.Tunneling
        http_proxy_options.auth_type = http.HttpProxyAuthenticationType.Nothing

        def sign_function(transform_args, **kwargs):
            transform_args.set_done()

        client = Client(bootstrap, ClientTlsContext(tls_ctx_options))
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=input_port,
            use_websockets=True,
            websocket_handshake_transform=sign_function,
            proxy_options=http_proxy_options)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)


if __name__ == 'main':
    unittest.main()
