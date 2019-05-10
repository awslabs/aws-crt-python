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
from concurrent.futures import Future
from enum import IntEnum
from awscrt.io import ClientBootstrap, ClientTlsContext

class QoS(IntEnum):
    """Quality of Service"""
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2

class ConnectReturnCode(IntEnum):
    ACCEPTED = 0
    UNACCEPTABLE_PROTOCOL_VERSION = 1
    IDENTIFIER_REJECTED = 2
    SERVER_UNAVAILABLE = 3
    BAD_USERNAME_OR_PASSWORD = 4
    NOT_AUTHORIZED = 5

class Will(object):
    __slots__ = ('topic', 'qos', 'payload', 'retain')

    def __init__(self, topic, qos, payload, retain):
        self.topic = topic
        self.qos = qos
        self.payload = payload
        self.retain = retain

class Client(object):
    __slots__ = ('_internal_client', 'bootstrap', 'tls_ctx')

    def __init__(self, bootstrap, tls_ctx = None):
        assert isinstance(bootstrap, ClientBootstrap)
        assert tls_ctx is None or isinstance(tls_ctx, ClientTlsContext)

        self.bootstrap = bootstrap
        self.tls_ctx = tls_ctx
        self._internal_client = _aws_crt_python.aws_py_mqtt_client_new(self.bootstrap._internal_bootstrap)

class Connection(object):
    __slots__ = ('_internal_connection', 'client')

    def __init__(self,
            client,
            on_connection_interrupted=None,
            on_connection_resumed=None,
            reconnect_min_timeout_sec=5.0,
            reconnect_max_timeout_sec=60.0):
        """
        on_connection_interrupted: optional callback, with signature (error_code)
        on_connection_resumed: optional callback, with signature (error_code, session_present)
        """

        assert isinstance(client, Client)
        self.client = client

        self._internal_connection = _aws_crt_python.aws_py_mqtt_client_connection_new(
            client._internal_client,
            on_connection_interrupted,
            on_connection_resumed,
            )

    def connect(self,
            client_id,
            host_name, port,
            use_websocket=False,
            clean_session=True, keep_alive=0,
            ping_timeout=0,
            will=None,
            username=None, password=None,
            connect_timeout_sec=5.0):

        future = Future()

        def on_connect(error_code, return_code, session_present):
            if error_code == 0 and return_code == 0:
                future.set_result(dict(session_present=session_present))
            else:
                future.set_exception(Exception("Error during connect: err={} rc={}".format(error_code, return_code)))

        try:
            assert will is None or isinstance(will, Will)
            assert use_websocket == False

            tls_ctx_cap = None
            if self.client.tls_ctx:
                tls_ctx_cap = self.client.tls_ctx._internal_tls_ctx

            _aws_crt_python.aws_py_mqtt_client_connection_connect(
                self._internal_connection,
                client_id,
                host_name,
                port,
                tls_ctx_cap,
                keep_alive,
                ping_timeout,
                will,
                username,
                password,
                on_connect,
                )

        except Exception as e:
            future.set_exception(e)

        return future

    def reconnect(self):
        future = Future()

        def on_connect(error_code, return_code, session_present):
            if error_code == 0 and return_code == 0:
                future.set_result(dict(session_present=session_present))
            else:
                future.set_exception(Exception("Error during reconnect"))

        try:
            _aws_crt_python.aws_py_mqtt_client_connection_reconnect(self._internal_connection, on_connect)
        except Exception as e:
            future.set_exception(e)

        return future

    def disconnect(self):

        future = Future()

        def on_disconnect():
            future.set_result(dict())

        try:
            _aws_crt_python.aws_py_mqtt_client_connection_disconnect(self._internal_connection, on_disconnect)
        except Exception as e:
            future.set_exception(e)

        return future

    def subscribe(self, topic, qos, callback):
        """
        callback: callback with signature (topic, message)
        """
        future = Future()
        packet_id = 0

        def suback(packet_id, topic, qos):
            future.set_result(dict(
                packet_id=packet_id,
                topic=topic,
                qos=QoS(qos),
            ))

        try:
            packet_id = _aws_crt_python.aws_py_mqtt_client_connection_subscribe(self._internal_connection, topic, qos.value, callback, suback)
        except Exception as e:
            future.set_exception(e)

        return future, packet_id

    def unsubscribe(self, topic):
        future = Future()
        packet_id = 0

        def unsuback(packet_id):
            future.set_result(dict(
                packet_id=packet_id
            ))

        try:
            packet_id = _aws_crt_python.aws_py_mqtt_client_connection_unsubscribe(self._internal_connection, topic, unsuback)

        except Exception as e:
            future.set_exception(e)

        return future, packet_id

    def publish(self, topic, payload, qos, retain=False):
        future = Future()
        packet_id = 0

        def puback(packet_id):
            future.set_result(dict(
                packet_id=packet_id
            ))

        try:
            packet_id = _aws_crt_python.aws_py_mqtt_client_connection_publish(self._internal_connection, topic, payload, qos.value, retain, puback)
        except Exception as e:
            future.set_exception(e)

        return future, packet_id

    def ping(self):
        _aws_crt_python.aws_py_mqtt_client_connection_ping(self._internal_connection)
