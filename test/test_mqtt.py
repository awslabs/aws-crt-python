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
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, LogLevel, init_logging
from awscrt.mqtt import Client, Connection, QoS
from test import NativeResourceTest
from concurrent.futures import Future
import os
import unittest
import boto3
import botocore.exceptions
import time
import uuid
import warnings


class MqttClientTest(NativeResourceTest):
    def test_lifetime(self):
        client = Client(ClientBootstrap(EventLoopGroup()))


class Config:
    cache = None

    def __init__(self, endpoint, cert, key):
        self.cert = cert
        self.key = key
        self.endpoint = endpoint

    @staticmethod
    def get():
        if Config.cache:
            return Config.cache

        # boto3 caches the HTTPS connection for the API calls, which appears to the unit test
        # framework as a leak, so ignore it, that's not what we're testing here
        try:
            warnings.simplefilter('ignore', ResourceWarning)
        except NameError:  # Python 2 has no ResourceWarning
            pass

        secrets = boto3.client('secretsmanager')
        response = secrets.get_secret_value(SecretId='unit-test/endpoint')
        endpoint = response['SecretString']
        response = secrets.get_secret_value(SecretId='unit-test/certificate')
        cert = response['SecretString'].encode('utf8')
        response = secrets.get_secret_value(SecretId='unit-test/privatekey')
        key = response['SecretString'].encode('utf8')
        Config.cache = Config(endpoint, cert, key)
        return Config.cache


class MqttConnectionTest(NativeResourceTest):
    TEST_TOPIC = '/test/me/senpai'
    TEST_MSG = 'NOTICE ME!'.encode('utf8')
    TIMEOUT = 10.0

    def _test_connection(self):
        try:
            config = Config.get()
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as ex:
            return self.skipTest("No credentials")

        tls_opts = TlsContextOptions.create_client_with_mtls(config.cert, config.key)
        tls = ClientTlsContext(tls_opts)
        client = Client(ClientBootstrap(EventLoopGroup()), tls)
        connection = Connection(client)
        connection.connect('aws-crt-python-unit-test-{0}'.format(uuid.uuid4()),
                           config.endpoint, 8883).result(self.TIMEOUT)
        return connection

    def test_connect_disconnect(self):
        connection = self._test_connection()
        connection.disconnect().result(self.TIMEOUT)

    def test_pub_sub(self):
        connection = self._test_connection()
        received = Future()

        def on_message(topic, payload):
            received.set_result((topic, payload))

        # subscribe
        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE, on_message)
        suback = subscribed.result(self.TIMEOUT)
        self.assertEqual(packet_id, suback['packet_id'])
        self.assertEqual(self.TEST_TOPIC, suback['topic'])
        self.assertIs(QoS.AT_LEAST_ONCE, suback['qos'])

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(self.TIMEOUT)
        self.assertEqual(packet_id, puback['packet_id'])

        # receive message
        rcv_topic, rcv_payload = received.result(self.TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv_topic)
        self.assertEqual(self.TEST_MSG, rcv_payload)

        # unsubscribe
        unsubscribed, packet_id = connection.unsubscribe(self.TEST_TOPIC)
        unsuback = unsubscribed.result(self.TIMEOUT)
        self.assertEqual(packet_id, unsuback['packet_id'])

        # disconnect
        connection.disconnect().result(self.TIMEOUT)

    def test_on_message(self):
        connection = self._test_connection()
        received = Future()

        def on_message(topic, payload):
            received.set_result((topic, payload))

        connection.on_message(on_message)

        # subscribe without callback
        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE)
        subscribed.result(self.TIMEOUT)

        # publish
        published, packet_id = connection.publish(self.TEST_TOPIC, self.TEST_MSG, QoS.AT_LEAST_ONCE)
        puback = published.result(self.TIMEOUT)

        # receive message
        rcv_topic, rcv_payload = received.result(self.TIMEOUT)
        self.assertEqual(self.TEST_TOPIC, rcv_topic)
        self.assertEqual(self.TEST_MSG, rcv_payload)

        # disconnect
        connection.disconnect().result(self.TIMEOUT)


if __name__ == 'main':
    unittest.main()
