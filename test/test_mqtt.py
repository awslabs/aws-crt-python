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

class MqttClientTest(NativeResourceTest):
    def test_lifetime(self):
        client = Client(ClientBootstrap(EventLoopGroup()))

class Credentials:
    def __init__(self):
        try:
            self.cert = os.environ['AWS_PY_MQTT_CERT']
            self.key = os.environ['AWS_PY_MQTT_KEY']
            self.ca = os.environ['AWS_PY_MQTT_CA']
            self.endpoint = os.environ['AWS_PY_MQTT_ENDPOINT']
            self.valid = True
        except:
            self.valid = False

class MqttConnectionTest(NativeResourceTest):
    def test_iot_service(self):
        creds = Credentials()
        if not creds.valid: return

