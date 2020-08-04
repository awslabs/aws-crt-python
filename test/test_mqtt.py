# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from __future__ import absolute_import
from awscrt import awsiot_mqtt_connection_builder
from awscrt.auth import AwsCredentialsProvider
from awscrt.http import HttpProxyOptions
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, LogLevel, init_logging
from awscrt.mqtt import Client, Connection, QoS
from test import NativeResourceTest
from concurrent.futures import Future
import os
import unittest
import boto3
import botocore.exceptions
import shutil
import tempfile
import time
import uuid
import warnings

TIMEOUT = 10.0
PROXY_HOST = os.environ.get('proxyhost')
PROXY_PORT = int(os.environ.get('proxyport', '0'))


class MqttClientTest(NativeResourceTest):
    def test_lifetime(self):
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        client = Client(bootstrap)


class Config:
    cache = None

    def __init__(self, endpoint, cert, key, region, cognito_creds):
        self.cert = cert
        self.key = key
        self.endpoint = endpoint
        self.region = region
        self.cognito_creds = cognito_creds

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
            response = secrets.get_secret_value(SecretId='unit-test/cognitopool')
            cognito_pool = response['SecretString']

            cognito = boto3.client('cognito-identity')
            response = cognito.get_id(IdentityPoolId=cognito_pool)
            cognito_id = response['IdentityId']
            response = cognito.get_credentials_for_identity(IdentityId=cognito_id)
            cognito_creds = response['Credentials']

            Config.cache = Config(endpoint, cert, key, region, cognito_creds)
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
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        tls_opts = TlsContextOptions.create_client_with_mtls(config.cert, config.key)
        tls = ClientTlsContext(tls_opts)

        client = Client(bootstrap, tls)
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

        # unsubscribe
        unsubscribed, packet_id = connection.unsubscribe(self.TEST_TOPIC)
        unsuback = unsubscribed.result(TIMEOUT)
        self.assertEqual(packet_id, unsuback['packet_id'])

        # disconnect
        connection.disconnect().result(TIMEOUT)

    def test_on_message(self):
        config = Config.get()
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        tls_opts = TlsContextOptions.create_client_with_mtls(config.cert, config.key)
        tls = ClientTlsContext(tls_opts)

        client = Client(bootstrap, tls)
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=config.endpoint,
            port=8883)
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

        # disconnect
        connection.disconnect().result(TIMEOUT)


class MqttBuilderTest(NativeResourceTest):
    def _test_connection(self, connection):
        connection.connect().result(TIMEOUT)
        connection.disconnect().result(TIMEOUT)

    def test_mtls_from_bytes(self):
        config = Config.get()
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        connection = awsiot_mqtt_connection_builder.mtls_from_bytes(
            cert_bytes=config.cert,
            pri_key_bytes=config.key,
            endpoint=config.endpoint,
            client_id=create_client_id(),
            client_bootstrap=bootstrap)
        self._test_connection(connection)

    def test_mtls_from_path(self):
        config = Config.get()
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)

        # test "from path" builder by writing secrets to tempfiles
        tmp_dirpath = tempfile.mkdtemp()
        try:
            cert_filepath = os.path.join(tmp_dirpath, 'cert')
            with open(cert_filepath, 'wb') as cert_file:
                cert_file.write(config.cert)

            key_filepath = os.path.join(tmp_dirpath, 'key')
            with open(key_filepath, 'wb') as key_file:
                key_file.write(config.key)

            connection = awsiot_mqtt_connection_builder.mtls_from_path(
                cert_filepath=cert_filepath,
                pri_key_filepath=key_filepath,
                endpoint=config.endpoint,
                client_id=create_client_id(),
                client_bootstrap=bootstrap)

        finally:
            shutil.rmtree(tmp_dirpath)

        self._test_connection(connection)

    def test_websockets_default(self):
        config = Config.get()
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        cred_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
        connection = awsiot_mqtt_connection_builder.websockets_with_default_aws_signing(
            region=config.region,
            credentials_provider=cred_provider,
            endpoint=config.endpoint,
            client_id=create_client_id(),
            client_bootstrap=bootstrap)
        self._test_connection(connection)

    def test_websockets_sts(self):
        """Websocket connection with X-Amz-Security-Token query param"""
        config = Config.get()
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        cred_provider = AwsCredentialsProvider.new_static(
            access_key_id=config.cognito_creds['AccessKeyId'],
            secret_access_key=config.cognito_creds['SecretKey'],
            session_token=config.cognito_creds['SessionToken'])
        connection = awsiot_mqtt_connection_builder.websockets_with_default_aws_signing(
            region=config.region,
            credentials_provider=cred_provider,
            endpoint=config.endpoint,
            client_id=create_client_id(),
            client_bootstrap=bootstrap)
        self._test_connection(connection)

    @unittest.skipIf(PROXY_HOST is None, 'requires "proxyhost" and "proxyport" env vars')
    def test_websockets_proxy(self):
        config = Config.get()
        elg = EventLoopGroup()
        resolver = DefaultHostResolver(elg)
        bootstrap = ClientBootstrap(elg, resolver)
        cred_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
        connection = awsiot_mqtt_connection_builder.websockets_with_default_aws_signing(
            credentials_provider=cred_provider,
            websocket_proxy_options=HttpProxyOptions(PROXY_HOST, PROXY_PORT),
            endpoint=config.endpoint,
            region=config.region,
            client_id=create_client_id(),
            client_bootstrap=bootstrap)
        self._test_connection(connection)


if __name__ == 'main':
    unittest.main()
