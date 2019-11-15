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

import _awscrt
import warnings
from concurrent.futures import Future
from enum import IntEnum
from awscrt import NativeResource
from awscrt.io import ClientBootstrap, ClientTlsContext, SocketOptions


class QoS(IntEnum):
    """Quality of Service"""
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


def _try_qos(qos_value):
    """Return None if the value cannot be converted to Qos (ex: 0x80 subscribe failure)"""
    try:
        return QoS(qos_value)
    except Exception:
        return None


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


class Client(NativeResource):
    __slots__ = ('tls_ctx')

    def __init__(self, bootstrap, tls_ctx=None):
        assert isinstance(bootstrap, ClientBootstrap)
        assert tls_ctx is None or isinstance(tls_ctx, ClientTlsContext)

        super(Client, self).__init__()
        self.tls_ctx = tls_ctx
        self._binding = _awscrt.mqtt_client_new(bootstrap, tls_ctx)


class Connection(NativeResource):
    __slots__ = ('client')

    def __init__(self,
                 client,
                 on_connection_interrupted=None,
                 on_connection_resumed=None,
                 reconnect_min_timeout_sec=5.0,
                 reconnect_max_timeout_sec=60.0):
        """
        on_connection_interrupted: optional callback, with signature (connection, error_code)
        on_connection_resumed: optional callback, with signature (connection, error_code, session_present)
        """

        assert isinstance(client, Client)
        assert callable(on_connection_interrupted) or on_connection_interrupted is None
        assert callable(on_connection_resumed) or on_connection_resumed is None

        super(Connection, self).__init__()
        self.client = client

        def _on_connection_interrupted(error_code):
            if on_connection_interrupted:
                on_connection_interrupted(self, error_code)
        def _on_connection_resumed(error_code, session_present):
            if on_connection_resumed:
                on_connection_resumed(self, error_code, session_present)

        self._binding = _awscrt.mqtt_client_connection_new(
            client,
            _on_connection_interrupted,
            _on_connection_resumed,
        )

    def connect(self,
                client_id,
                host_name, port,
                use_websocket=False,
                clean_session=True, keep_alive=0,
                ping_timeout=0,
                will=None,
                username=None, password=None,
                socket_options=SocketOptions(),
                **kwargs):

        future = Future()

        # Handle deprecated parameters
        if 'connect_timeout_sec' in kwargs:
            warnings.warn(
                "connect_timeout_sec parameter is deprecated, please set socket_options instead.",
                DeprecationWarning)
            socket_options.connect_timeout_ms = kwargs['connect_timeout_sec'] * 1000

        def on_connect(error_code, return_code, session_present):
            if error_code == 0 and return_code == 0:
                future.set_result(dict(session_present=session_present))
            else:
                future.set_exception(Exception("Error during connect: err={} rc={}".format(error_code, return_code)))

        try:
            assert will is None or isinstance(will, Will)
            assert isinstance(socket_options, SocketOptions)
            assert use_websocket == False

            _awscrt.mqtt_client_connection_connect(
                self._binding,
                client_id,
                host_name,
                port,
                socket_options,
                self.client.tls_ctx,
                keep_alive,
                ping_timeout,
                will,
                username,
                password,
                clean_session,
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
            _awscrt.mqtt_client_connection_reconnect(self._binding, on_connect)
        except Exception as e:
            future.set_exception(e)

        return future

    def disconnect(self):

        future = Future()

        def on_disconnect():
            future.set_result(dict())

        try:
            _awscrt.mqtt_client_connection_disconnect(self._binding, on_disconnect)
        except Exception as e:
            future.set_exception(e)

        return future

    def subscribe(self, topic, qos, callback):
        """
        callback: callback with signature (topic, message)
        """

        future = Future()
        packet_id = 0

        def suback(packet_id, topic, qos, error_code):
            if error_code:
                future.set_exception(Exception(error_code))  # TODO: Actual exceptions for error_codes
            else:
                qos = _try_qos(qos)
                if qos is None:
                    future.set_exception(SubscribeError(topic))
                else:
                    future.set_result(dict(
                        packet_id=packet_id,
                        topic=topic,
                        qos=qos,
                    ))

        try:
            assert callable(callback)
            assert isinstance(qos, QoS)
            packet_id = _awscrt.mqtt_client_connection_subscribe(self._binding, topic, qos.value, callback, suback)
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
            packet_id = _awscrt.mqtt_client_connection_unsubscribe(self._binding, topic, unsuback)

        except Exception as e:
            future.set_exception(e)

        return future, packet_id

    def resubscribe_existing_topics(self):
        """
        Subscribe again to all current topics.
        This is to help when resuming a connection with a clean session.

        Returns (future, packet_id).
        When the resubscribe is complete, the future will contain a dict. The dict will contain:
        ['packet_id']: the packet ID of the server's response, or None if there were no topics to resubscribe to.
        ['topics']: A list of (topic, qos) tuples, where qos will be None if the topic failed to resubscribe.
        If there were no topics to resubscribe to then the list will be empty.
        """
        packet_id = 0
        future = Future()

        def on_suback(packet_id, topic_qos_tuples, error_code):
            if error_code:
                future.set_exception(Exception(error_code))  # TODO: Actual exceptions for error_codes
            else:
                future.set_result(dict(
                    packet_id=packet_id,
                    topics=[(topic, _try_qos(qos)) for (topic, qos) in topic_qos_tuples],
                ))

        try:
            packet_id = _awscrt.mqtt_client_connection_resubscribe_existing_topics(self._binding, on_suback)
            if packet_id is None:
                # There were no topics to resubscribe to.
                future.set_result(dict(packet_id=None, topics=[]))

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
            packet_id = _awscrt.mqtt_client_connection_publish(self._binding, topic, payload, qos.value, retain, puback)
        except Exception as e:
            future.set_exception(e)

        return future, packet_id


class SubscribeError(Exception):
    """
    Subscription rejected by server.
    """
    pass
