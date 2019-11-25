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
from awscrt.http import HttpProxyOptions, HttpRequest
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
    def __init__(self,
                 client,
                 host_name,
                 port,
                 client_id,
                 clean_session=True,
                 on_connection_interrupted=None,
                 on_connection_resumed=None,
                 reconnect_min_timeout_secs=5,
                 reconnect_max_timeout_secs=60,
                 keep_alive_secs=3600,
                 ping_timeout_ms=3000,
                 will=None,
                 username=None,
                 password=None,
                 socket_options=None,
                 use_websockets=False,
                 websocket_proxy_options=None,
                 websocket_handshake_transform=None,
                 ):
        """
        Arguments:
            client (Client): MQTT Client

            host_name (str): Server name to connect to.

            port (int): Server port to connect to.

            client_id (str): ID to place in CONNECT packet. Must be unique across all devices/clients.
                    If an ID is already in use, the other client will be disconnected.

            clean_session (bool): Whether or not to start a clean session with each reconnect.
                    If True, the server will forget all subscriptions with each reconnect.
                    Set False to request that the server resume an existing session
                    or start a new session that may be resumed after a connection loss.
                    The `session_present` bool in the connection callback informs
                    whether an existing session was successfully resumed.
                    If an existing session is resumed, the server remembers previous subscriptions
                    and sends mesages (with QoS1 or higher) that were published while the client was offline.

            on_connection_interrupted (function): Optional callback with signature:
                    (Connection, awscrt.exceptions.AwsCrtError) -> None
                    Invoked when the MQTT connection is lost.
                    The MQTT client will automatically attempt to reconnect.

            on_connection_resumed (function): Optional callback with signature:
                    (Connection, ConnectReturnCode, session_present: bool) -> None
                    Invoked when the MQTT connection is automatically resumed.

            reconnect_min_timeout_secs (int): Minimum time to wait between reconnect attempts.
                Wait starts at min and doubles with each attempt until max is reached.

            reconnect_max_timeout_secs (int): Maximum time to wait between reconnect attempts.
                Wait starts at min and doubles with each attempt until max is reached.

            keep_alive_secs (int): The keep alive value, in seconds, to send in CONNECT packet.
                        A PING will automatically be sent at this interval.
                        The server will assume the connection is lost if no PING is received after 1.5X this value.
                        This value must be higher than ping_timeout_ms.

            ping_timeout_ms (int): Milliseconds to wait for ping response before client assumes
                        the connection is invalid and attempts to reconnect.
                        This value must be less than keep_alive.
                        Alternatively, TCP keep-alive may accomplish this in a more efficient (low-power) scenario,
                        but keep-alive options may not work the same way on every platform and OS version.

            will (awscrt.mqtt.Will): Will to send with CONNECT packet. The will is
                        published by the server when its connection to the client
                        is unexpectedly lost.

            username (str): Username to connect with.

            password (str): Password to connect with.

            socket_options: awscrt.io.SocketOptions

            use_websocket: If true, connect to MQTT over websockets.

            websocket_proxy_options: optional awscrt.http.HttpProxyOptions for
                    websocket connections.

            websocket_handshake_transform: optional function with signature:
                    (WebsocketHandshakeTransformArgs) -> None
                    If provided, function is called each time a websocket connection
                    is attempted. The function may modify the websocket handshake
                    request. See WebsocketHandshakeTransformArgs for more info.
        """

        assert isinstance(client, Client)
        assert callable(on_connection_interrupted) or on_connection_interrupted is None
        assert callable(on_connection_resumed) or on_connection_resumed is None
        assert isinstance(will, Will) or will is None
        assert isinstance(socket_options, SocketOptions) or socket_options is None
        assert isinstance(websocket_proxy_options, HttpProxyOptions) or websocket_proxy_options is None
        assert callable(websocket_handshake_transform) or websocket_handshake_transform is None

        super(Connection, self).__init__()

        # init-only
        self.client = client
        self._on_connection_interrupted_cb = on_connection_interrupted
        self._on_connection_resumed_cb = on_connection_resumed
        self._use_websockets = use_websockets
        self._ws_handshake_transform_cb = websocket_handshake_transform

        # may be changed at runtime, take effect the the next time connect/reconnect occurs
        self.client_id = client_id
        self.host_name = host_name
        self.port = port
        self.clean_session = clean_session
        self.keep_alive_secs = keep_alive_secs
        self.ping_timeout_ms = ping_timeout_ms
        self.will = will
        self.username = username
        self.password = password
        self.socket_options = socket_options if socket_options else SocketOptions()
        self.websocket_proxy_options = websocket_proxy_options

        # TODO: reconnect_min_timeout_secs & reconnect_max_timeout_secs currently unused

        self._binding = _awscrt.mqtt_client_connection_new(
            self,
            client,
            use_websockets,
        )

    def _on_connection_interrupted(self, error_code):
        if self._on_connection_interrupted_cb:
            self._on_connection_interrupted_cb(self, error_code)

    def _on_connection_resumed(self, error_code, session_present):
        if self._on_connection_resumed_cb:
            self._on_connection_resumed_cb(self, error_code, session_present)

    def _ws_handshake_transform(self, http_request_binding, http_headers_binding, native_userdata):
        if self._ws_handshake_transform_cb is None:
            _awscrt.mqtt_ws_handshake_transform_complete(None, native_userdata)
            return

        def _on_complete(f):
            _awscrt.mqtt_ws_handshake_transform_complete(f.exception(), native_userdata)

        future = Future()
        future.add_done_callback(_on_complete)
        http_request = HttpRequest._from_bindings(http_request_binding, http_headers_binding)
        transform_args = WebsocketHandshakeTransformArgs(self, http_request, future)
        try:
            self._ws_handshake_transform_cb(transform_args)
        except Exception as e:
            # Call set_done() if user failed to do so before uncaught exception was raised,
            # there's a chance the callback wasn't callable and user has no idea we tried to hand them the baton.
            if not future.done():
                transform_args.set_done(e)

    def connect(self):
        future = Future()

        def on_connect(error_code, return_code, session_present):
            if error_code == 0 and return_code == 0:
                future.set_result(dict(session_present=session_present))
            else:
                future.set_exception(Exception("Error during connect: err={} rc={}".format(error_code, return_code)))

        try:
            _awscrt.mqtt_client_connection_connect(
                self._binding,
                self.client_id,
                self.host_name,
                self.port,
                self.socket_options,
                self.client.tls_ctx,
                self.keep_alive_secs,
                self.ping_timeout_ms,
                self.will,
                self.username,
                self.password,
                self.clean_session,
                on_connect,
                self.websocket_proxy_options
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

    def subscribe(self, topic, qos, callback=None):
        """
        callback: optional callback with signature (topic, message)
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
            assert callable(callback) or callback is None
            assert isinstance(qos, QoS)
            packet_id = _awscrt.mqtt_client_connection_subscribe(self._binding, topic, qos.value, callback, suback)
        except Exception as e:
            future.set_exception(e)

        return future, packet_id

    def on_message(self, callback):
        """
        callback: callback with signature (topic, message), or None to disable.
        """
        assert callable(callback) or callback is None
        _awscrt.mqtt_client_connection_on_message(self._binding, callback)

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


class WebsocketHandshakeTransformArgs(object):
    """
    Argument to a "websocket_handshake_transform" function.

    -- Attributes --
    mqtt_connection: awscrt.mqtt.Connection this handshake is for.
    http_request: awscrt.http.HttpRequest for this handshake.

    A websocket_handshake_transform function has signature:
    (WebsocketHandshakeTransformArgs) -> None

    The function implementer may modify transform_args.http_request as desired.
    They MUST call transform_args.set_done() when complete, passing an
    exception if something went wrong. Failure to call set_done()
    will hang the application.

    The implementor may do asynchronous work before calling transform_args.set_done(),
    they are not required to call set_done() within the scope of the transform function.
    An example of async work would be to fetch credentials from another service,
    sign the request headers, and finally call set_done() to mark the transform complete.

    The default websocket handshake request uses path "/mqtt".
    All required headers are present,
    plus the optional header "Sec-WebSocket-Protocol: mqtt".
    """

    def __init__(self, mqtt_connection, http_request, done_future):
        self.mqtt_connection = mqtt_connection
        self.http_request = http_request
        self._done_future = done_future

    def set_done(self, exception=None):
        """
        Mark the transformation complete.
        If exception is passed in, the handshake is canceled.
        """
        if exception is None:
            self._done_future.set_result(None)
        else:
            self._done_future.set_exception(exception)


class SubscribeError(Exception):
    """
    Subscription rejected by server.
    """
    pass
