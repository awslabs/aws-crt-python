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
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from awscrt.mqtt import Client, Connection
from test import NativeResourceTest
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
        except:
            self.valid = False

    @staticmethod
    def get():
        try:
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
        except:
            pass

class MqttConnectionTest(NativeResourceTest):
    def _test_connection(self):
        config = Config.get()
        tls_opts = TlsContextOptions.create_client_with_mtls(config.cert, config.key)
        if config.ca:
            tls_opts.override_default_trust_store(config.ca)
        tls = ClientTlsContext(tls_opts)
        client = Client(ClientBootstrap(EventLoopGroup()), tls)
        connection = Connection(client)
        connection.connect('aws-crt-python-unit-test-'.format(time.gmtime()), config.endpoint, 8883).result()
        connection.disconnect().result()

    def test_iot_service(self):
        warnings.simplefilter('ignore', ResourceWarning)
        self._test_connection()

if __name__ == 'main':
    unittest.main()

        
        

        
        


