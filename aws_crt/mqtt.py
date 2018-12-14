# Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import _aws_crt_python
from aws_crt.io import ClientBootstrap

def _default_on_connect(return_code, session_present):
    pass
def _default_on_disconnect(return_code):
    return False

QoS = type('QoS', (), dict(
    AtMostOnce = 0,
    AtLeastOnce = 1,
    ExactlyOnce = 2,
))

class Will(object):
    __slots__ = ['topic', 'qos', 'payload', 'retain']

    def __init__(self, topic, qos, payload, retain):
        self.topic = topic
        self.qos = qos
        self.payload = payload
        self.retain = retain

class Client(object):
    __slots__ = ['_internal_client', 'bootstrap', 'tls_ctx']

    def __init__(self, bootstrap, tls_ctx = None):
        assert isinstance(bootstrap, ClientBootstrap)
        assert tls_ctx is None or isinstance(tls_ctx, io.ClientTlsContext)

        self.bootstrap = bootstrap
        self.tls_ctx = tls_ctx
        self._internal_client = _aws_crt_python.aws_py_mqtt_client_new(self.bootstrap._internal_bootstrap)

class Connection(object):
    __slots__ = ['_internal_connection', 'client', 'client_id', 'will']

    def __init__(self, client, client_id):

        assert isinstance(client, Client)

        self.client = client
        self.client_id = client_id

    def connect(self,
            host_name, port,
            on_connect=_default_on_connect,
            on_disconnect=_default_on_disconnect,
            use_websocket=False, alpn=None,
            clean_session=True, keep_alive=0,
            will=None,
            username=None, password=None):

        assert use_websocket == False

        assert will is None or isinstance(will, Will)

        tls_ctx_cap = None
        if self.client.tls_ctx:
            tls_ctx_cap = self.client.tls_ctx._internal_tls_ctx

        self._internal_connection = _aws_crt_python.aws_py_mqtt_client_connection_new(
            self.client._internal_client,
            tls_ctx_cap,
            host_name,
            port,
            self.client_id,
            keep_alive,
            on_connect,
            on_disconnect,
            will,
            username,
            password,
            )

    def disconnect(self):
        return _aws_crt_python.aws_py_mqtt_client_connection_disconnect(self._internal_connection)

    def subscribe(self, topic, qos, callback, suback_callback=None):
        return _aws_crt_python.aws_py_mqtt_client_connection_subscribe(self._internal_connection, topic, qos, callback, suback_callback)

    def unsubscribe(self, topic, unsuback_callback=None):
        return _aws_crt_python.aws_py_mqtt_client_connection_unsubscribe(self._internal_connection, topic, unsuback_callback)

    def publish(self, topic, payload, qos, retain=False, puback_callback=None):
        _aws_crt_python.aws_py_mqtt_client_connection_publish(self._internal_connection, topic, payload, qos, retain, puback_callback)

    def ping(self):
        _aws_crt_python.aws_py_mqtt_client_connection_ping(self._internal_connection)