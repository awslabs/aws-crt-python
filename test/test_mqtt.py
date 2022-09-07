# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, Pkcs11Lib, TlsContextOptions, LogLevel, init_logging
from awscrt.mqtt import Client, Connection, QoS
from test import NativeResourceTest
from concurrent.futures import Future
import enum
import os
import pathlib
import sys
import unittest
import uuid

TIMEOUT = 100.0


class MqttClientTest(NativeResourceTest):
    def test_lifetime(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap)


AuthType = enum.Enum('AuthType', ['CERT_AND_KEY', 'PKCS11', 'ECC_CERT_AND_KEY'])


class Config:
    def __init__(self, auth_type):
        self.endpoint = self._get_env('AWS_TEST_IOT_MQTT_ENDPOINT')
        self.cert_path = self._get_env('AWS_TEST_TLS_CERT_PATH')
        self.cert = pathlib.Path(self.cert_path).read_text().encode('utf-8')

        if auth_type == AuthType.ECC_CERT_AND_KEY:
            self.key_path = self._get_env('AWS_TEST_ECC_KEY_PATH')
            self.key = pathlib.Path(self.key_path).read_text().encode('utf-8')
            self.cert_path = self._get_env('AWS_TEST_ECC_CERT_PATH')
            self.cert = pathlib.Path(self.cert_path).read_text().encode('utf-8')

        if auth_type == AuthType.CERT_AND_KEY:
            self.key_path = self._get_env('AWS_TEST_TLS_KEY_PATH')
            self.key = pathlib.Path(self.key_path).read_text().encode('utf-8')

        elif auth_type == AuthType.PKCS11:
            self.pkcs11_lib_path = self._get_env('AWS_TEST_PKCS11_LIB')
            self.pkcs11_pin = self._get_env('AWS_TEST_PKCS11_PIN')
            self.pkcs11_token_label = self._get_env('AWS_TEST_PKCS11_TOKEN_LABEL')
            self.pkcs11_key_label = self._get_env('AWS_TEST_PKCS11_KEY_LABEL')

    def _get_env(self, name):
        val = os.environ.get(name)
        if not val:
            raise unittest.SkipTest(f"test requires env var: {name}")
        return val


def create_client_id():
    return 'aws-crt-python-unit-test-{0}'.format(uuid.uuid4())


class MqttConnectionTest(NativeResourceTest):
    TEST_TOPIC = '/test/me/senpai'
    TEST_MSG = 'NOTICE ME!'.encode('utf8')

    def _create_connection(self, auth_type=AuthType.CERT_AND_KEY, use_static_singletons=False):
        config = Config(auth_type)

        if auth_type == AuthType.CERT_AND_KEY or auth_type == AuthType.ECC_CERT_AND_KEY:
            tls_opts = TlsContextOptions.create_client_with_mtls_from_path(config.cert_path, config.key_path)
            tls = ClientTlsContext(tls_opts)

        elif auth_type == AuthType.PKCS11:
            try:
                pkcs11_lib = Pkcs11Lib(
                    file=config.pkcs11_lib_path,
                    behavior=Pkcs11Lib.InitializeFinalizeBehavior.STRICT)

                tls_opts = TlsContextOptions.create_client_with_mtls_pkcs11(
                    pkcs11_lib=pkcs11_lib,
                    user_pin=config.pkcs11_pin,
                    token_label=config.pkcs11_token_label,
                    private_key_label=config.pkcs11_key_label,
                    cert_file_path=config.cert_path)

                tls = ClientTlsContext(tls_opts)

            except Exception as e:
                if 'AWS_ERROR_UNIMPLEMENTED' in str(e):
                    raise unittest.SkipTest(f'TLS with PKCS#11 not supported on this platform ({sys.platform})')
                else:
                    # re-raise exception
                    raise

        if use_static_singletons:
            client = Client(tls_ctx=tls)
        else:
            elg = EventLoopGroup()
            resolver = DefaultHostResolver(elg)
            bootstrap = ClientBootstrap(elg, resolver)
            client = Client(bootstrap, tls)

        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=config.endpoint,
            port=8883)
        return connection

    def test_connect_disconnect(self):
        connection = self._create_connection()
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_ecc_connect_disconnect(self):
        connection = self._create_connection(AuthType.ECC_CERT_AND_KEY)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_pkcs11(self):
        connection = self._create_connection(AuthType.PKCS11)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_pub_sub(self):
        connection = self._create_connection()
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

    def test_on_message(self):
        connection = self._create_connection()
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
        connection = self._create_connection()

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
        connection = self._create_connection(use_static_singletons=True)
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

        # free singletons
        ClientBootstrap.release_static_default()
        EventLoopGroup.release_static_default()
        DefaultHostResolver.release_static_default()


if __name__ == 'main':
    unittest.main()
