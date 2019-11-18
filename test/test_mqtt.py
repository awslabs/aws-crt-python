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
import time
import warnings


class MqttClientTest(NativeResourceTest):
    def test_lifetime(self):
        client = Client(ClientBootstrap(EventLoopGroup()))


class Config:
    def __init__(self, endpoint, cert, key, ca=None):
        try:
            self.cert = cert
            self.key = key
            self.ca = ca
            self.endpoint = endpoint
            self.valid = True
        except BaseException:
            self.valid = False

    @staticmethod
    def get():
        # boto3 caches the HTTPS connection for the API calls, which appears to the unit test
        # framework as a leak, so ignore it, that's not what we're testing here
        warnings.simplefilter('ignore', ResourceWarning)

        secrets = boto3.client('secretsmanager')
        response = secrets.get_secret_value(SecretId='unit-test/endpoint')
        endpoint = response['SecretString']
        response = secrets.get_secret_value(SecretId='unit-test/certificate')
        cert = bytes(response['SecretString'], 'utf8')
        response = secrets.get_secret_value(SecretId='unit-test/privatekey')
        key = bytes(response['SecretString'], 'utf8')
        response = secrets.get_secret_value(SecretId='unit-test/ca')
        ca = bytes(response['SecretString'], 'utf8')
        return Config(endpoint, cert, key, ca)


class MqttConnectionTest(NativeResourceTest):
    TEST_TOPIC = '/test/me/senpai'
    TEST_MSG = 'NOTICE ME!'

    def _test_connection(self):
        try:
            config = Config.get()
        except Exception as ex:
            return self.skipTest("No credentials")

        try:
            tls_opts = TlsContextOptions.create_client_with_mtls(config.cert, config.key)
            if config.ca:
                tls_opts.override_default_trust_store(config.ca)
            tls = ClientTlsContext(tls_opts)
            client = Client(ClientBootstrap(EventLoopGroup()), tls)
            connection = Connection(client)
            connection.connect('aws-crt-python-unit-test-'.format(time.gmtime()), config.endpoint, 8883).result()
            return connection
        except Exception as ex:
            self.assertFalse(ex)

    def test_connect_disconnect(self):
        init_logging(LogLevel.Trace, 'stdout')
        connection = self._test_connection()
        connection.disconnect().result()
        init_logging(LogLevel.NoLogs, 'stdout')

    def test_pub_sub(self):
        connection = self._test_connection()
        disconnected = Future()

        def on_disconnect(result):
            disconnected.set_result(True)

        def on_message(topic, payload):
            self.assertEqual(self.TEST_TOPIC, topic)
            self.assertEqual(self.TEST_MSG, str(payload, 'utf8'))
            connection.unsubscribe(self.TEST_TOPIC)
            connection.disconnect().add_done_callback(on_disconnect)

        def do_publish(result):
            connection.publish(self.TEST_TOPIC, bytes(self.TEST_MSG, 'utf8'), QoS.AT_LEAST_ONCE)

        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE, on_message)
        subscribed.add_done_callback(do_publish)

        disconnected.result()

    def test_sub_to_any(self):
        connection = self._test_connection()
        disconnected = Future()

        def on_disconnect(result):
            disconnected.set_result(True)

        def on_message(topic, payload):
            self.assertEqual(self.TEST_TOPIC, topic)
            self.assertEqual(self.TEST_MSG, str(payload, 'utf8'))
            connection.unsubscribe(self.TEST_TOPIC)
            connection.disconnect().add_done_callback(on_disconnect)

        def do_publish(result):
            connection.publish(self.TEST_TOPIC, bytes(self.TEST_MSG, 'utf8'), QoS.AT_LEAST_ONCE)

        connection.subscribe_to_any(on_message).result()
        subscribed, packet_id = connection.subscribe(self.TEST_TOPIC, QoS.AT_LEAST_ONCE)
        subscribed.add_done_callback(do_publish)

        disconnected.result()


if __name__ == 'main':
    unittest.main()
