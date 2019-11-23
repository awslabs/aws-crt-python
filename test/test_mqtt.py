# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

from __future__ import absolute_import
from awscrt import awsiot_mqtt_connection_builder
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, LogLevel, init_logging
from awscrt.mqtt import Client, Connection, QoS
from test import NativeResourceTest
from concurrent.futures import Future
import os
import unittest
import boto3
import botocore.exceptions
import tempfile
import time
import uuid
import warnings

TIMEOUT = 10.0


class MqttClientTest(NativeResourceTest):
    def test_lifetime(self):
        client = Client(ClientBootstrap(EventLoopGroup()))


class Config:
    cache = None

    def __init__(self, endpoint, cert, key, region):
        self.cert = cert
        self.key = key
        self.endpoint = endpoint
        self.region = region

    @staticmethod
    def get():
        """Raises SkipTest if credentials aren't set up correctly"""
        if Config.cache:
            return Config.cache

        # boto3 caches the HTTPS connection for the API calls, which appears to the unit test
        # framework as a leak, so ignore it, that's not what we're testing here
        try:
            warnings.simplefilter('ignore', ResourceWarning)
        except NameError:  # Python 2 has no ResourceWarning
            pass

        try:
            secrets = boto3.client('secretsmanager')
            response = secrets.get_secret_value(SecretId='unit-test/endpoint')
            endpoint = response['SecretString']
            response = secrets.get_secret_value(SecretId='unit-test/certificate')
            cert = response['SecretString'].encode('utf8')
            response = secrets.get_secret_value(SecretId='unit-test/privatekey')
            key = response['SecretString'].encode('utf8')
            region = secrets.meta.region_name
            Config.cache = Config(endpoint, cert, key, region)
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as ex:
            raise unittest.SkipTest("No credentials")

        return Config.cache


def create_client_id():
    return 'aws-crt-python-unit-test-{0}'.format(uuid.uuid4())


class MqttConnectionTest(NativeResourceTest):
    TEST_TOPIC = '/test/me/senpai'
    TEST_MSG = 'NOTICE ME!'.encode('utf8')

    def _test_connection(self):
        config = Config.get()

        tls_opts = TlsContextOptions.create_client_with_mtls(config.cert, config.key)
        tls = ClientTlsContext(tls_opts)
        client = Client(ClientBootstrap(EventLoopGroup()), tls)
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=config.endpoint,
            port=8883)
        connection.connect().result(TIMEOUT)
        return connection

    def test_connect_disconnect(self):
        connection = self._test_connection()
        connection.disconnect().result(TIMEOUT)

    def test_pub_sub(self):
        connection = self._test_connection()
        received = Future()

        def on_message(topic, payload):
            received.set_result((topic, payload))

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
        rcv_topic, rcv_payload = received.result(TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv_topic)
        self.assertEqual(self.TEST_MSG, rcv_payload)

        # unsubscribe
        unsubscribed, packet_id = connection.unsubscribe(self.TEST_TOPIC)
        unsuback = unsubscribed.result(TIMEOUT)
        self.assertEqual(packet_id, unsuback['packet_id'])

        # disconnect
        connection.disconnect().result(TIMEOUT)

    def test_on_message(self):
        connection = self._test_connection()
        received = Future()

        def on_message(topic, payload):
            received.set_result((topic, payload))

        connection.on_message(on_message)

        # subscribe without callback
        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE)
        subscribed.result(TIMEOUT)

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(TIMEOUT)

        # receive message
        rcv_topic, rcv_payload = received.result(TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv_topic)
        self.assertEqual(self.TEST_MSG, rcv_payload)

        # disconnect
        connection.disconnect().result(TIMEOUT)


class MqttBuilderTest(unittest.TestCase):# DO NOT COMMIT THIS LINE (NativeResourceTest):
    def _create_bootstrap(self):
        elg = EventLoopGroup(1)
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        return bootstrap

    def _test_connection(self, connection):
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mtls_from_bytes(self):
        config = Config.get()
        connection = awsiot_mqtt_connection_builder.mtls_from_bytes(
            cert_bytes=config.cert,
            pri_key_bytes=config.key,
            endpoint=config.endpoint,
            client_id=create_client_id(),
            client_bootstrap=self._create_bootstrap())
        self._test_connection(connection)

    def test_mtls_from_path(self):
        config = Config.get()

        # test "from path" builder by writing secrets to tempfiles
        with tempfile.NamedTemporaryFile() as cert_file:
            with tempfile.NamedTemporaryFile() as key_file:
                cert_file.write(config.cert)
                cert_file.flush()

                key_file.write(config.key)
                key_file.flush()

                connection = awsiot_mqtt_connection_builder.mtls_from_path(
                    cert_filepath=cert_file.name,
                    pri_key_filepath=key_file.name,
                    endpoint=config.endpoint,
                    client_id=create_client_id(),
                    client_bootstrap=self._create_bootstrap())

        self._test_connection(connection)

    def test_websockets_default(self):
        config = Config.get()
        connection = awsiot_mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=config.endpoint,
            region=config.region,
            client_id=create_client_id(),
            client_bootstrap=self._create_bootstrap())
        self._test_connection(connection)


if __name__ == 'main':
    unittest.main()
