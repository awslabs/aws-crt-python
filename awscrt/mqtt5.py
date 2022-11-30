"""
MQTT5

"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
from typing import Any, Callable
import _awscrt
from concurrent.futures import Future
from enum import IntEnum
from awscrt import NativeResource, exceptions
from awscrt.http import HttpProxyOptions, HttpRequest
from awscrt.io import ClientBootstrap, SocketOptions, ClientTlsContext
from dataclasses import dataclass
from collections.abc import Sequence
from inspect import signature


class QoS(IntEnum):
    """MQTT message delivery quality of service.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901234>`__ encoding values.
    """

    AT_MOST_ONCE = 0
    """
    The message is delivered according to the capabilities of the underlying network. No response is sent by the
    receiver and no retry is performed by the sender. The message arrives at the receiver either once or not at all.
    """

    AT_LEAST_ONCE = 1
    """
    A level of service that ensures that the message arrives at the receiver at least once.
    """

    EXACTLY_ONCE = 2
    """
    A level of service that ensures that the message arrives at the receiver exactly once.

    Note that this client does not currently support QoS 2 as of (August 2022)
    """


def _try_qos(value):
    try:
        return QoS(value)
    except Exception:
        return None


class ConnectReasonCode(IntEnum):
    """Server return code for connect attempts.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901079>`__ encoding values.
    """

    SUCCESS = 0
    """
    Returned when the connection is accepted.
    """

    UNSPECIFIED_ERROR = 128
    """
    Returned when the server has a failure but does not want to specify a reason or none
    of the other reason codes apply.
    """

    MALFORMED_PACKET = 129
    """
    Returned when data in the CONNECT packet could not be correctly parsed by the server.
    """

    PROTOCOL_ERROR = 130
    """
    Returned when data in the CONNECT packet does not conform to the MQTT5 specification requirements.
    """

    IMPLEMENTATION_SPECIFIC_ERROR = 131
    """
    Returned when the CONNECT packet is valid but was not accepted by the server.
    """

    UNSUPPORTED_PROTOCOL_VERSION = 132
    """
    Returned when the server does not support MQTT5 protocol version specified in the connection.
    """

    CLIENT_IDENTIFIER_NOT_VALID = 133
    """
    Returned when the client identifier in the CONNECT packet is a valid string but not one that
    is allowed on the server.
    """

    BAD_USERNAME_OR_PASSWORD = 134
    """
    Returned when the server does not accept the username and/or password specified by the client
    in the connection packet.
    """

    NOT_AUTHORIZED = 135
    """
    Returned when the client is not authorized to connect to the server.
    """

    SERVER_UNAVAILABLE = 136
    """
    Returned when the MQTT5 server is not available.
    """

    SERVER_BUSY = 137
    """
    Returned when the server is too busy to make a connection. It is recommended that the client try again later.
    """

    BANNED = 138
    """
    Returned when the client has been banned by the server.
    """

    BAD_AUTHENTICATION_METHOD = 140
    """
    Returned when the authentication method used in the connection is either not supported on the server or it does
    not match the authentication method currently in use in the CONNECT packet.
    """

    TOPIC_NAME_INVALID = 144
    """
    Returned when the Will topic name sent in the CONNECT packet is correctly formed, but is not accepted by
    the server.
    """

    PACKET_TOO_LARGE = 149
    """
    Returned when the CONNECT packet exceeded the maximum permissible size on the server.
    """

    QUOTA_EXCEEDED = 151
    """
    Returned when the quota limits set on the server have been met and/or exceeded.
    """

    PAYLOAD_FORMAT_INVALID = 153
    """
    Returned when the Will payload in the CONNECT packet does not match the specified payload format indicator.
    """

    RETAIN_NOT_SUPPORTED = 154
    """
    Returned when the server does not retain messages but the CONNECT packet on the client had Will retain enabled.
    """

    QOS_NOT_SUPPORTED = 155
    """
    Returned when the server does not support the QOS setting set in the Will QOS in the CONNECT packet.
    """

    USE_ANOTHER_SERVER = 156
    """
    Returned when the server is telling the client to temporarily use another server instead of the one they
    are trying to connect to.
    """

    SERVER_MOVED = 157
    """
    Returned when the server is telling the client to permanently use another server instead of the one they
    are trying to connect to.
    """

    CONNECTION_RATE_EXCEEDED = 159
    """
    Returned when the server connection rate limit has been exceeded.
    """


def _try_connect_reason_code(value):
    try:
        return ConnectReasonCode(value)
    except Exception:
        return None


class DisconnectReasonCode(IntEnum):
    """Reason code inside DISCONNECT packets.  Helps determine why a connection was terminated.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901208>`__ encoding values.
    """

    NORMAL_DISCONNECTION = 0
    """
    Returned when the remote endpoint wishes to disconnect normally. Will not trigger the publish of a Will message if a
    Will message was configured on the connection.

    May be sent by the client or server.
    """

    DISCONNECT_WITH_WILL_MESSAGE = 4
    """
    Returns when the client wants to disconnect but requires that the server publish the Will message configured
    on the connection.

    May only be sent by the client.
    """

    UNSPECIFIED_ERROR = 128
    """
    Returned when the connection was closed but the sender does not want to specify a reason or none
    of the other reason codes apply.

    May be sent by the client or the server.
    """

    MALFORMED_PACKET = 129
    """
    Indicates the remote endpoint received a packet that does not conform to the MQTT specification.

    May be sent by the client or the server.
    """

    PROTOCOL_ERROR = 130
    """
    Returned when an unexpected or out-of-order packet was received by the remote endpoint.

    May be sent by the client or the server.
    """

    IMPLEMENTATION_SPECIFIC_ERROR = 131
    """
    Returned when a valid packet was received by the remote endpoint, but could not be processed by the current implementation.

     May be sent by the client or the server.
    """

    NOT_AUTHORIZED = 135
    """
    Returned when the remote endpoint received a packet that represented an operation that was not authorized within
    the current connection.

    May only be sent by the server.
    """

    SERVER_BUSY = 137
    """
    Returned when the server is busy and cannot continue processing packets from the client.

    May only be sent by the server.
    """

    SERVER_SHUTTING_DOWN = 139
    """
    Returned when the server is shutting down.

    May only be sent by the server.
    """

    KEEP_ALIVE_TIMEOUT = 141
    """
    Returned when the server closes the connection because no packet from the client has been received in
    1.5 times the KeepAlive time set when the connection was established.

    May only be sent by the server.
    """

    SESSION_TAKEN_OVER = 142
    """
    Returned when the server has established another connection with the same client ID as a client's current
    connection, causing the current client to become disconnected.

    May only be sent by the server.
    """

    TOPIC_FILTER_INVALID = 143
    """
    Returned when the topic filter name is correctly formed but not accepted by the server.

    May only be sent by the server.
    """

    TOPIC_NAME_INVALID = 144
    """
    Returned when topic name is correctly formed, but is not accepted.

    May be sent by the client or the server.
    """

    RECEIVE_MAXIMUM_EXCEEDED = 147
    """
    Returned when the remote endpoint reached a state where there were more in-progress QoS1+ publishes then the
    limit it established for itself when the connection was opened.

    May be sent by the client or the server.
    """

    TOPIC_ALIAS_INVALID = 148
    """
    Returned when the remote endpoint receives a PUBLISH packet that contained a topic alias greater than the
    maximum topic alias limit that it established for itself when the connection was opened.

    May be sent by the client or the server.
    """

    PACKET_TOO_LARGE = 149
    """
    Returned when the remote endpoint received a packet whose size was greater than the maximum packet size limit
    it established for itself when the connection was opened.

    May be sent by the client or the server.
    """

    MESSAGE_RATE_TOO_HIGH = 150
    """
    Returned when the remote endpoint's incoming data rate was too high.

    May be sent by the client or the server.
    """

    QUOTA_EXCEEDED = 151
    """
    Returned when an internal quota of the remote endpoint was exceeded.

    May be sent by the client or the server.
    """

    ADMINISTRATIVE_ACTION = 152
    """
    Returned when the connection was closed due to an administrative action.

    May be sent by the client or the server.
    """

    PAYLOAD_FORMAT_INVALID = 153
    """
    Returned when the remote endpoint received a packet where payload format did not match the format specified
    by the payload format indicator.

    May be sent by the client or the server.
    """

    RETAIN_NOT_SUPPORTED = 154
    """
    Returned when the server does not support retained messages.

    May only be sent by the server.
    """

    QOS_NOT_SUPPORTED = 155
    """
    Returned when the client sends a QoS that is greater than the maximum QoS established when the connection was
    opened.

    May only be sent by the server.
    """

    USE_ANOTHER_SERVER = 156
    """
    Returned by the server to tell the client to temporarily use a different server.

    May only be sent by the server.
    """

    SERVER_MOVED = 157
    """
    Returned by the server to tell the client to permanently use a different server.

    May only be sent by the server.
    """

    SHARED_SUBSCRIPTIONS_NOT_SUPPORTED = 158
    """
    Returned by the server to tell the client that shared subscriptions are not supported on the server.

    May only be sent by the server.
    """

    CONNECTION_RATE_EXCEEDED = 159
    """
    Returned when the server disconnects the client due to the connection rate being too high.

    May only be sent by the server.
    """

    MAXIMUM_CONNECT_TIME = 160
    """
    Returned by the server when the maximum connection time authorized for the connection was exceeded.

    May only be sent by the server.
    """

    SUBSCRIPTION_IDENTIFIERS_NOT_SUPPORTED = 161
    """
    Returned by the server when it received a SUBSCRIBE packet with a subscription identifier, but the server does
    not support subscription identifiers.

    May only be sent by the server.
    """

    WILDCARD_SUBSCRIPTIONS_NOT_SUPPORTED = 162
    """
    Returned by the server when it received a SUBSCRIBE packet with a wildcard topic filter, but the server does
    not support wildcard topic filters.

    May only be sent by the server.
    """


def _try_disconnect_reason_code(value):
    try:
        return DisconnectReasonCode(value)
    except Exception:
        return None


class PubackReasonCode(IntEnum):
    """Reason code inside PUBACK packets that indicates the result of the associated PUBLISH request.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901124>`__ encoding values.
    """

    SUCCESS = 0
    """
    Returned when the (QoS 1) publish was accepted by the recipient.

    May be sent by the client or the server.
    """

    NO_MATCHING_SUBSCRIBERS = 16
    """
    Returned when the (QoS 1) publish was accepted but there were no matching subscribers.

    May only be sent by the server.
    """

    UNSPECIFIED_ERROR = 128
    """
    Returned when the (QoS 1) publish was not accepted and the receiver does not want to specify a reason or none
    of the other reason codes apply.

    May be sent by the client or the server.
    """

    IMPLEMENTATION_SPECIFIC_ERROR = 131
    """
    Returned when the (QoS 1) publish was valid but the receiver was not willing to accept it.

    May be sent by the client or the server.
    """

    NOT_AUTHORIZED = 135
    """
    Returned when the (QoS 1) publish was not authorized by the receiver.

    May be sent by the client or the server.
    """

    TOPIC_NAME_INVALID = 144
    """
    Returned when the topic name was valid but the receiver was not willing to accept it.

    May be sent by the client or the server.
    """

    PACKET_IDENTIFIER_IN_USE = 145
    """
    Returned when the packet identifier used in the associated PUBLISH was already in use.
    This can indicate a mismatch in the session state between client and server.

    May be sent by the client or the server.
    """

    QUOTA_EXCEEDED = 151
    """
    Returned when the associated PUBLISH failed because an internal quota on the recipient was exceeded.

    May be sent by the client or the server.
    """

    PAYLOAD_FORMAT_INVALID = 153
    """
    Returned when the PUBLISH packet's payload format did not match its payload format indicator property.

    May be sent by the client or the server.
    """


def _try_puback_reason_code(value):
    try:
        return PubackReasonCode(value)
    except Exception:
        return None


class SubackReasonCode(IntEnum):
    """Reason code inside SUBACK packet payloads.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901178>`__ encoding values.

    This will only be sent by the server and not the client.
    """

    GRANTED_QOS_0 = 0
    """
    Returned when the subscription was accepted and the maximum QoS sent will be QoS 0.
    """

    GRANTED_QOS_1 = 1
    """
    Returned when the subscription was accepted and the maximum QoS sent will be QoS 1.
    """

    GRANTED_QOS_2 = 2
    """
    Returned when the subscription was accepted and the maximum QoS sent will be QoS 2.
    """

    UNSPECIFIED_ERROR = 128
    """
    Returned when the connection was closed but the sender does not want to specify a reason or none
    of the other reason codes apply.
    """

    IMPLEMENTATION_SPECIFIC_ERROR = 131
    """
    Returned when the subscription was valid but the server did not accept it.
    """

    NOT_AUTHORIZED = 135
    """
    Returned when the client was not authorized to make the subscription on the server.
    """

    TOPIC_FILTER_INVALID = 143
    """
    Returned when the subscription topic filter was correctly formed but not allowed for the client.
    """

    PACKET_IDENTIFIER_IN_USE = 145
    """
    Returned when the packet identifier was already in use on the server.
    """

    QUOTA_EXCEEDED = 151
    """
    Returned when a subscribe-related quota set on the server was exceeded.
    """

    SHARED_SUBSCRIPTIONS_NOT_SUPPORTED = 158
    """
    Returned when the subscription's topic filter was a shared subscription and the server does not support
    shared subscriptions.
    """

    SUBSCRIPTION_IDENTIFIERS_NOT_SUPPORTED = 161
    """
    Returned when the SUBSCRIBE packet contained a subscription identifier and the server does not support
    subscription identifiers.
    """

    WILDCARD_SUBSCRIPTIONS_NOT_SUPPORTED = 162
    """
    Returned when the subscription's topic filter contains a wildcard but the server does not support
    wildcard subscriptions.
    """


def _try_suback_reason_code(value):
    try:
        return SubackReasonCode(value)
    except Exception:
        return None


class UnsubackReasonCode(IntEnum):
    """Reason codes inside UNSUBACK packet payloads that specify the results for each topic filter in the associated
    UNSUBSCRIBE packet.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901194>`__ encoding values.
    """

    SUCCESS = 0
    """
    Returned when the unsubscribe was successful and the client is no longer subscribed to the topic filter on the server.
    """

    NO_SUBSCRIPTION_EXISTED = 17
    """
    Returned when the topic filter did not match one of the client's existing topic filters on the server.
    """

    UNSPECIFIED_ERROR = 128
    """
    Returned when the unsubscribe of the topic filter was not accepted and the server does not want to specify a
    reason or none of the other reason codes apply.
    """

    IMPLEMENTATION_SPECIFIC_ERROR = 131
    """
    Returned when the topic filter was valid but the server does not accept an unsubscribe for it.
    """

    NOT_AUTHORIZED = 135
    """
    Returned when the client was not authorized to unsubscribe from that topic filter on the server.
    """

    TOPIC_NAME_INVALID = 144
    """
    Returned when the topic filter was correctly formed but is not allowed for the client on the server.
    """

    PACKET_IDENTIFIER_IN_USE = 145
    """
    Returned when the packet identifier was already in use on the server.
    """


def _try_unsuback_reason_code(value):
    try:
        return UnsubackReasonCode(value)
    except Exception:
        return None


class ClientSessionBehaviorType(IntEnum):
    """Controls how the mqtt client should behave with respect to MQTT sessions.
    """

    DEFAULT = 0
    """
    Default client session behavior. Maps to CLEAN.
    """

    CLEAN = 1
    """
    Always ask for a clean session when connecting
    """

    REJOIN_POST_SUCCESS = 2
    """
    Always attempt to rejoin an existing session after an initial connection success.

    Session rejoin requires an appropriate non-zero session expiry interval in the client's CONNECT options.
    """


class PacketType(IntEnum):
    """MQTT5 Packet Type enumeration
    """

    NONE = -1
    """
    internal indicator that the associated packet is None
    """

    RESERVED = 0
    """
    Reserved
    """

    CONNECT = 1
    """
    Connection request
    """

    CONNACK = 2
    """
    Connect acknowledgment
    """

    PUBLISH = 3
    """
    Publish message"""

    PUBACK = 4
    """
    Publish acknowledgment (QoS 1)
    """

    PUBREC = 5
    """
    Publish received (QoS 2 delivery part 1)
    """

    PUBREL = 6
    """
    Publish release (QoS 2 delivery part 2)
    """

    PUBCOMP = 7
    """
    Publish complete (QoS 2 delivery part 3)
    """

    SUBSCRIBE = 8
    """
    Subscribe request
    """

    SUBACK = 9
    """
    Subscribe acknowledgment
    """

    UNSUBSCRIBE = 10
    """
    Unsubscribe request
    """

    UNSUBACK = 11
    """
    Unsubscribe acknowledgment
    """

    PINGREQ = 12
    """
    PING request
    """

    PINGRESP = 13
    """
    PING response
    """

    DISCONNECT = 14
    """
    Disconnect notification
    """

    AUTH = 15
    """
    Authentication exchange
    """


class PayloadFormatIndicator(IntEnum):
    """Optional property describing a PUBLISH payload's format.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901111>`__ encoding values.
    """

    AWS_MQTT5_PFI_BYTES = 0
    """
    The payload is arbitrary binary data
    """

    AWS_MQTT5_PFI_UTF8 = 1
    """
    The payload is a well-formed utf-8 string value.
    """


class RetainAndHandlingType(IntEnum):
    """Configures how retained messages should be handled when subscribing with a topic filter that matches topics with
    associated retained messages.

    Enum values match `MQTT5 spec <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901169>`_ encoding values.
    """

    SEND_ON_SUBSCRIBE = 0
    """
    The server should always send all retained messages on topics that match a subscription's filter.
    """

    SEND_ON_SUBSCRIBE_IF_NEW = 1
    """
    The server should send retained messages on topics that match the subscription's filter, but only for the
    first matching subscription, per session.
    """

    DONT_SEND = 2
    """
    Subscriptions must not trigger any retained message publishes from the server.
    """


class ExtendedValidationAndFlowControlOptions(IntEnum):
    """Additional controls for client behavior with respect to operation validation and flow control; these checks
    go beyond the MQTT5 spec to respect limits of specific MQTT brokers.
    """

    NONE = 0
    """
    Do not do any additional validation or flow control
    """

    AWS_IOT_CORE_DEFAULTS = 1
    """
    Apply additional client-side validation and operational flow control that respects the
    default AWS IoT Core limits.

    Currently applies the following additional validation:

    * No more than 8 subscriptions per SUBSCRIBE packet
    * Topics and topic filters have a maximum of 7 slashes (8 segments), not counting any AWS rules prefix
    * Topics must be 256 bytes or less in length
    * Client id must be 128 or less bytes in length

    Also applies the following flow control:

    * Outbound throughput throttled to 512KB/s
    * Outbound publish TPS throttled to 100

    """


class ClientOperationQueueBehaviorType(IntEnum):
    """Controls how disconnects affect the queued and in-progress operations tracked by the client.  Also controls
    how operations are handled while the client is not connected.  In particular, if the client is not connected,
    then any operation that would be failed on disconnect (according to these rules) will be rejected.
    """

    DEFAULT = 0
    """
    Default client operation queue behavior. Maps to FAIL_QOS0_PUBLISH_ON_DISCONNECT.
    """

    FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT = 1
    """
    Re-queues QoS 1+ publishes on disconnect; un-acked publishes go to the front while unprocessed publishes stay
    in place.  All other operations (QoS 0 publishes, subscribe, unsubscribe) are failed.
    """

    FAIL_QOS0_PUBLISH_ON_DISCONNECT = 2
    """
    QoS 0 publishes that are not complete at the time of disconnection are failed.  Un-acked QoS 1+ publishes are
    re-queued at the head of the line for immediate retransmission on a session resumption.  All other operations
    are requeued in original order behind any retransmissions.
    """

    FAIL_ALL_ON_DISCONNECT = 3
    """
    All operations that are not complete at the time of disconnection are failed, except operations that
    the MQTT5 spec requires to be retransmitted (un-acked QoS1+ publishes).
    """


class ExponentialBackoffJitterMode(IntEnum):
    """Controls how the reconnect delay is modified in order to smooth out the distribution of reconnection attempt
    timepoints for a large set of reconnecting clients.

    See `Exponential Backoff and Jitter <https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/>`_
    """

    DEFAULT = 0
    """
    Maps to Full
    """

    NONE = 1
    """
    Do not perform any randomization on the reconnect delay
    """

    FULL = 2
    """
    Fully random between no delay and the current exponential backoff value.
    """

    DECORRELATED = 3
    """
    Backoff is taken randomly from the interval between the base backoff
    interval and a scaling (greater than 1) of the current backoff value
    """


@dataclass
class UserProperty:
    """MQTT5 User Property

    Args:
        name (str): Property name
        value (str): Property value
    """

    name: str = None
    value: str = None


def _init_user_properties(user_properties_tuples):
    if user_properties_tuples is None:
        return None

    return [UserProperty(name=name, value=value) for (name, value) in user_properties_tuples]


@dataclass
class NegotiatedSettings:
    """
    Mqtt behavior settings that are dynamically negotiated as part of the CONNECT/CONNACK exchange.

    While you can infer all of these values from a combination of:
    - defaults as specified in the mqtt5 spec
    - your CONNECT settings
    - the CONNACK from the broker

    the client instead does the combining for you and emits a NegotiatedSettings object with final, authoritative values.

    Negotiated settings are communicated with every successful connection establishment.

    Args:
        maximum_qos (QoS): The maximum QoS allowed for publishes on this connection instance
        session_expiry_interval_sec (int): The amount of time in seconds the server will retain the MQTT session after a disconnect.
        receive_maximum_from_server (int): The number of in-flight QoS 1 and QoS 2 publications the server is willing to process concurrently.
        maximum_packet_size_to_server (int): The maximum packet size the server is willing to accept.
        topic_alias_maximum_to_server (int): Not Currently Supported
        topic_alias_maximum_to_client (int): Not Currently Supported
        server_keep_alive_sec (int): The maximum amount of time in seconds between client packets. The client should use PINGREQs to ensure this limit is not breached.  The server will disconnect the client for inactivity if no MQTT packet is received in a time interval equal to 1.5 x this value.
        retain_available (bool): Whether the server supports retained messages.
        wildcard_subscriptions_available (bool): Whether the server supports wildcard subscriptions.
        subscription_identifiers_available (bool): Whether the server supports subscription identifiers
        shared_subscriptions_available (bool): Whether the server supports shared subscriptions
        rejoined_session (bool): Whether the client has rejoined an existing session.
    """
    maximum_qos: QoS = None
    session_expiry_interval_sec: int = None
    receive_maximum_from_server: int = None
    maximum_packet_size_to_server: int = None
    topic_alias_maximum_to_server: int = None
    topic_alias_maximum_to_client: int = None
    server_keep_alive_sec: int = None
    retain_available: bool = None
    wildcard_subscriptions_available: bool = None
    subscription_identifiers_available: bool = None
    shared_subscriptions_available: bool = None
    rejoined_session: bool = None


@dataclass
class ConnackPacket:
    """Data model of an `MQTT5 CONNACK <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901074>`_ packet.

    Args:
        session_present (bool): True if the client rejoined an existing session on the server, false otherwise.
        reason_code (ConnectReasonCode): Indicates either success or the reason for failure for the connection attempt. session_expiry_interval_sec (int): A time interval, in seconds, that the server will persist this connection's MQTT session state for.  If present, this value overrides any session expiry specified in the preceding CONNECT packet.
        receive_maximum (int): The maximum amount of in-flight QoS 1 or 2 messages that the server is willing to handle at once. If omitted or None, the limit is based on the valid MQTT packet id space (65535).
        maximum_qos (QoS): The maximum message delivery quality of service that the server will allow on this connection.
        retain_available (bool): Indicates whether the server supports retained messages.  If None, retained messages are supported.
        maximum_packet_size (int): Specifies the maximum packet size, in bytes, that the server is willing to accept.  If None, there is no limit beyond what is imposed by the MQTT spec itself.
        assigned_client_identifier (str): Specifies a client identifier assigned to this connection by the server.  Only valid when the client id of the preceding CONNECT packet was left empty.
        reason_string (str): Additional diagnostic information about the result of the connection attempt.
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
        wildcard_subscriptions_available (bool): Indicates whether the server supports wildcard subscriptions.  If None, wildcard subscriptions are supported.
        subscription_identifiers_available (bool): Indicates whether the server supports subscription identifiers.  If None, subscription identifiers are supported.
        shared_subscription_available (bool): Indicates whether the server supports shared subscription topic filters.  If None, shared subscriptions are supported.
        server_keep_alive (int): Server-requested override of the keep alive interval, in seconds.  If None, the keep alive value sent by the client should be used.
        response_information (str): A value that can be used in the creation of a response topic associated with this connection. MQTT5-based request/response is outside the purview of the MQTT5 spec and this client.
        server_reference (str): Property indicating an alternate server that the client may temporarily or permanently attempt to connect to instead of the configured endpoint.  Will only be set if the reason code indicates another server may be used (ServerMoved, UseAnotherServer).
    """
    session_present: bool = None
    reason_code: ConnectReasonCode = None
    session_expiry_interval_sec: int = None
    receive_maximum: int = None
    maximum_qos: QoS = None
    retain_available: bool = None
    maximum_packet_size: int = None
    assigned_client_identifier: str = None
    reason_string: str = None
    user_properties: 'Sequence[UserProperty]' = None
    wildcard_subscriptions_available: bool = None
    subscription_identifiers_available: bool = None
    shared_subscription_available: bool = None
    server_keep_alive: int = None
    response_information: str = None
    server_reference: str = None


@dataclass
class DisconnectPacket:
    """Data model of an `MQTT5 DISCONNECT <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901205>`_ packet.

    Args:
        reason_code (DisconnectReasonCode): Value indicating the reason that the sender is closing the connection
        session_expiry_interval_sec (int): A change to the session expiry interval negotiated at connection time as part of the disconnect.  Only valid for DISCONNECT packets sent from client to server.  It is not valid to attempt to change session expiry from zero to a non-zero value.
        reason_string (str): Additional diagnostic information about the reason that the sender is closing the connection
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
        server_reference (str): Property indicating an alternate server that the client may temporarily or permanently attempt to connect to instead of the configured endpoint.  Will only be set if the reason code indicates another server may be used (ServerMoved, UseAnotherServer).

    """
    reason_code: DisconnectReasonCode = DisconnectReasonCode.NORMAL_DISCONNECTION
    session_expiry_interval_sec: int = None
    reason_string: str = None
    user_properties: 'Sequence[UserProperty]' = None
    server_reference: str = None


@dataclass
class Subscription:
    """Configures a single subscription within a Subscribe operation

    Args:
        topic_filter (str): The topic filter to subscribe to
        qos (QoS): The maximum QoS on which the subscriber will accept publish messages
        no_local (bool): Whether the server will not send publishes to a client when that client was the one who sent the publish
        retain_as_published (bool): Whether messages sent due to this subscription keep the retain flag preserved on the message
        retain_handling_type (RetainAndHandlingType): Whether retained messages on matching topics be sent in reaction to this subscription
    """
    topic_filter: str
    qos: QoS = QoS.AT_MOST_ONCE
    no_local: bool = False
    retain_as_published: bool = False
    retain_handling_type: RetainAndHandlingType = RetainAndHandlingType.SEND_ON_SUBSCRIBE


@dataclass
class SubscribePacket:
    """Data model of an `MQTT5 SUBSCRIBE <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901161>`_ packet.

    Args:
        subscriptions (Sequence[Subscription]): The list of topic filters that the client wishes to listen to
        subscription_identifier (int): The positive int to associate with all topic filters in this request.  Publish packets that match a subscription in this request should include this identifier in the resulting message.
        user_properties (Sequence[UserProperty]): The list of MQTT5 user properties included with the packet.
    """
    subscriptions: 'Sequence[Subscription]'
    subscription_identifier: int = None
    user_properties: 'Sequence[UserProperty]' = None


@dataclass
class SubackPacket:
    """Data model of an `MQTT5 SUBACK <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901171>`_ packet.

    Args:
        reason_string (str): Additional diagnostic information about the result of the SUBSCRIBE attempt.
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
        reason_codes (Sequence[SubackReasonCode]): List of reason codes indicating the result of each individual subscription entry in the associated SUBSCRIBE packet.
    """
    reason_string: str = None
    user_properties: 'Sequence[UserProperty]' = None
    reason_codes: 'Sequence[SubackReasonCode]' = None


@dataclass
class UnsubscribePacket:
    """Data model of an `MQTT5 UNSUBSCRIBE <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc384800445>`_ packet.

    Args:
        topic_filters (Sequence[str]): List of topic filters that the client wishes to unsubscribe from.
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
    """
    topic_filters: 'Sequence[str]'
    user_properties: 'Sequence[UserProperty]' = None


@dataclass
class UnsubackPacket:
    """Data model of an `MQTT5 UNSUBACK <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc471483687>`_ packet.

    Args:
        reason_string (str): Additional diagnostic information about the result of the UNSUBSCRIBE attempt.
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
        reason_codes (Sequence[DisconnectReasonCode]): A list of reason codes indicating the result of unsubscribing from each individual topic filter entry in the associated UNSUBSCRIBE packet.

    """
    reason_string: str = None
    user_properties: 'Sequence[UserProperty]' = None
    reason_codes: 'Sequence[DisconnectReasonCode]' = None


@dataclass
class PublishPacket:
    """Data model of an `MQTT5 PUBLISH <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901100>`_ packet

    Args:
        payload (Any): The payload of the publish message.
        qos (QoS): The MQTT quality of service associated with this PUBLISH packet.
        retain (bool): True if this is a retained message, false otherwise.
        topic (str): The topic associated with this PUBLISH packet.
        payload_format_indicator (PayloadFormatIndicator): Property specifying the format of the payload data. The mqtt5 client does not enforce or use this value in a meaningful way.
        message_expiry_interval_sec (int): Sent publishes - indicates the maximum amount of time allowed to elapse for message delivery before the server should instead delete the message (relative to a recipient). Received publishes - indicates the remaining amount of time (from the server's perspective) before the message would have been deleted relative to the subscribing client. If left None, indicates no expiration timeout.
        topic_alias (int): An integer value that is used to identify the Topic instead of using the Topic Name.
        response_topic (str): Opaque topic string intended to assist with request/response implementations.  Not internally meaningful to MQTT5 or this client.
        correlation_data (Any): Opaque binary data used to correlate between publish messages, as a potential method for request-response implementation.  Not internally meaningful to MQTT5.
        subscription_identifiers (Sequence[int]): The subscription identifiers of all the subscriptions this message matched.
        content_type (str): Property specifying the content type of the payload.  Not internally meaningful to MQTT5.
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
    """
    payload: Any = ""  # Unicode objects are converted to C strings using 'utf-8' encoding
    qos: QoS = QoS.AT_MOST_ONCE
    retain: bool = False
    topic: str = ""
    payload_format_indicator: PayloadFormatIndicator = None
    message_expiry_interval_sec: int = None
    topic_alias: int = None
    response_topic: str = None
    correlation_data: Any = None   # Unicode objects are converted to C strings using 'utf-8' encoding
    subscription_identifiers: 'Sequence[int]' = None  # ignore attempts to set but provide in received packets
    content_type: str = None
    user_properties: 'Sequence[UserProperty]' = None


@dataclass
class PubackPacket:
    """Data model of an `MQTT5 PUBACK <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901121>`_ packet

    Args:
        reason_code (PubackReasonCode): Success indicator or failure reason for the associated PUBLISH packet.
        reason_string (str): Additional diagnostic information about the result of the PUBLISH attempt.
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
    """
    reason_code: PubackReasonCode = None
    reason_string: str = None
    user_properties: 'Sequence[UserProperty]' = None


@dataclass
class ConnectPacket:
    """Data model of an `MQTT5 CONNECT <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901033>`_ packet.

    Args:
        keep_alive_interval_sec (int): The maximum time interval, in seconds, that is permitted to elapse between the point at which the client finishes transmitting one MQTT packet and the point it starts sending the next.  The client will use PINGREQ packets to maintain this property. If the responding CONNACK contains a keep alive property value, then that is the negotiated keep alive value. Otherwise, the keep alive sent by the client is the negotiated value.
        client_id (str): A unique string identifying the client to the server.  Used to restore session state between connections. If left empty, the broker will auto-assign a unique client id.  When reconnecting, the mqtt5 client will always use the auto-assigned client id.
        username (str): A string value that the server may use for client authentication and authorization.
        password (str): Opaque binary data that the server may use for client authentication and authorization.
        session_expiry_interval_sec (int): A time interval, in seconds, that the client requests the server to persist this connection's MQTT session state for.  Has no meaning if the client has not been configured to rejoin sessions.  Must be non-zero in order to successfully rejoin a session. If the responding CONNACK contains a session expiry property value, then that is the negotiated session expiry value.  Otherwise, the session expiry sent by the client is the negotiated value.
        request_response_information (bool): If true, requests that the server send response information in the subsequent CONNACK.  This response information may be used to set up request-response implementations over MQTT, but doing so is outside the scope of the MQTT5 spec and client.
        request_problem_information (bool): If true, requests that the server send additional diagnostic information (via response string or user properties) in DISCONNECT or CONNACK packets from the server.
        receive_maximum (int): Notifies the server of the maximum number of in-flight QoS 1 and 2 messages the client is willing to handle.  If omitted or None, then no limit is requested.
        maximum_packet_size (int): Notifies the server of the maximum packet size the client is willing to handle.  If omitted or None, then no limit beyond the natural limits of MQTT packet size is requested.
        will_delay_interval_sec (int): A time interval, in seconds, that the server should wait (for a session reconnection) before sending the will message associated with the connection's session.  If omitted or None, the server will send the will when the associated session is destroyed.  If the session is destroyed before a will delay interval has elapsed, then the will must be sent at the time of session destruction.
        will (PublishPacket): The definition of a message to be published when the connection's session is destroyed by the server or when the will delay interval has elapsed, whichever comes first.  If None, then nothing will be sent.
        user_properties (Sequence[UserProperty]): List of MQTT5 user properties included with the packet.
    """
    keep_alive_interval_sec: int = None
    client_id: str = None
    username: str = None
    password: str = None
    session_expiry_interval_sec: int = None
    request_response_information: bool = None
    request_problem_information: bool = None
    receive_maximum: int = None
    maximum_packet_size: int = None
    will_delay_interval_sec: int = None
    will: PublishPacket = None
    user_properties: 'Sequence[UserProperty]' = None


class WebsocketHandshakeTransformArgs:
    """
    Argument to a "websocket_handshake_transform" function.

    A websocket_handshake_transform function has signature:
    ``fn(transform_args: WebsocketHandshakeTransformArgs) -> None``

    The function implementer may modify `transform_args.http_request` as desired.
    They MUST call `transform_args.set_done()` when complete, passing an
    exception if something went wrong. Failure to call `set_done()`
    will hang the application.

    The implementer may do asynchronous work before calling `transform_args.set_done()`,
    they are not required to call `set_done()` within the scope of the transform function.
    An example of async work would be to fetch credentials from another service,
    sign the request headers, and finally call `set_done()` to mark the transform complete.

    The default websocket handshake request uses path "/mqtt".
    All required headers are present,
    plus the optional header "Sec-WebSocket-Protocol: mqtt".

    Args:
        client (Client): Client this handshake is for.
        http_request (awscrt.http.HttpRequest): HTTP request for this handshake.
        done_future (concurrent.futures.Future): Future to complete when the
            :meth:`set_done()` is called. It will contain None if successful,
            or an exception will be set.

    Attributes:
        client (Client): Client this handshake is for.
        http_request (awscrt.http.HttpRequest): HTTP request for this handshake.
    """

    def __init__(self, client, http_request, done_future):
        self.client = client
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


@dataclass
class PublishReceivedData:
    """Dataclass containing data related to a Publish Received Callback

    Args:
        publish_packet (PublishPacket): Data model of an `MQTT5 PUBLISH <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901100>`_ packet.
    """
    publish_packet: PublishPacket = None


@dataclass
class OperationStatisticsData:
    """Dataclass containing some simple statistics about the current state of the client's queue of operations

    Args:
        incomplete_operation_count (int): total number of operations submitted to the client that have not yet been completed.  Unacked operations are a subset of this.
        incomplete_operation_size (int): total packet size of operations submitted to the client that have not yet been completed.  Unacked operations are a subset of this.
        unacked_operation_count (int): total number of operations that have been sent to the server and are waiting for a corresponding ACK before they can be completed.
        unacked_operation_size (int): total packet size of operations that have been sent to the server and are waiting for a corresponding ACK before they can be completed.
    """
    incomplete_operation_count: int = 0
    incomplete_operation_size: int = 0
    unacked_operation_count: int = 0
    unacked_operation_size: int = 0


@dataclass
class LifecycleStoppedData:
    """Dataclass containing results of an Stopped Lifecycle Event
    Currently Unused"""
    pass


@dataclass
class LifecycleAttemptingConnectData:
    """Dataclass containing results of an Attempting Connect Lifecycle Event
    Currently Unused"""
    pass


@dataclass
class LifecycleConnectSuccessData:
    """Dataclass containing results of a Connect Success Lifecycle Event

    Args:
        connack_packet (ConnackPacket): Data model of an `MQTT5 CONNACK <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901074>`_ packet.
        negotiated_settings: (NegotiatedSettings): Mqtt behavior settings that have been dynamically negotiated as part of the CONNECT/CONNACK exchange.
    """
    connack_packet: ConnackPacket = None
    negotiated_settings: NegotiatedSettings = None


@dataclass
class LifecycleConnectFailureData:
    """Dataclass containing results of a Connect Failure Lifecycle Event

    Args:
        connack_packet (ConnackPacket):  Data model of an `MQTT5 CONNACK <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901074>`_ packet.
        error_code (int): (:class:`awscrt.exceptions.AwsCrtError`): Exception which caused connection failure.
    """
    connack_packet: ConnackPacket = None
    exception: Exception = None


@dataclass
class LifecycleDisconnectData:
    """Dataclass containing results of a Disconnect Lifecycle Event

    Args:
        disconnect_packet (DisconnectPacket): Data model of an `MQTT5 DISCONNECT <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html#_Toc3901205>`_ packet.
        error_code (int): (:class:`awscrt.exceptions.AwsCrtError`): Exception which caused disconnection.
    """
    disconnect_packet: DisconnectPacket = None
    exception: Exception = None


@dataclass
class PublishCompletionData:
    """Dataclass containing results of a Publish

    Args:
        puback (PubackPacket): On a successful completion of a QoS1 publish a PubackPacket will be included.
    """
    puback: PubackPacket = None  # This will be None on a QoS0


@dataclass
class ClientOptions:
    """Configuration for the creation of MQTT5 clients

    Args:
        host_name (str): Host name of the MQTT server to connect to.
        port (int): Network port of the MQTT server to connect to.
        bootstrap (ClientBootstrap): The Client bootstrap used
        socket_options (SocketOptions): The socket properties of the underlying MQTT connections made by the client or None if defaults are used.
        tls_ctx (ClientTlsContext): The TLS context for secure socket connections. If None, then a plaintext connection will be used.
        http_proxy_options (HttpProxyOptions): The (tunneling) HTTP proxy usage when establishing MQTT connections
        websocket_handshake_transform (Callable[[WebsocketHandshakeTransformArgs],]): This callback allows a custom transformation of the HTTP request that acts as the websocket handshake. Websockets will be used if this is set to a valid transformation callback.  To use websockets but not perform a transformation, just set this as a trivial completion callback.  If None, the connection will be made with direct MQTT.
        connect_options (ConnectPacket): All configurable options with respect to the CONNECT packet sent by the client, including the will. These connect properties will be used for every connection attempt made by the client.
        session_behavior (ClientSessionBehaviorType): How the MQTT5 client should behave with respect to MQTT sessions.
        extended_validation_and_flow_control_options (ExtendedValidationAndFlowControlOptions): The additional controls for client behavior with respect to operation validation and flow control; these checks go beyond the base MQTT5 spec to respect limits of specific MQTT brokers.
        offline_queue_behavior (ClientOperationQueueBehaviorType): Returns how disconnects affect the queued and in-progress operations tracked by the client.  Also controls how new operations are handled while the client is not connected.  In particular, if the client is not connected, then any operation that would be failed on disconnect (according to these rules) will also be rejected.
        retry_jitter_mode (ExponentialBackoffJitterMode): How the reconnect delay is modified in order to smooth out the distribution of reconnection attempt timepoints for a large set of reconnecting clients.
        min_reconnect_delay_ms (int): The minimum amount of time to wait to reconnect after a disconnect. Exponential backoff is performed with jitter after each connection failure.
        max_reconnect_delay_ms (int): The maximum amount of time to wait to reconnect after a disconnect.  Exponential backoff is performed with jitter after each connection failure.
        min_connected_time_to_reset_reconnect_delay_ms (int): The amount of time that must elapse with an established connection before the reconnect delay is reset to the minimum. This helps alleviate bandwidth-waste in fast reconnect cycles due to permission failures on operations.
        ping_timeout_ms (int): The time interval to wait after sending a PINGREQ for a PINGRESP to arrive. If one does not arrive, the client will close the current connection.
        connack_timeout_ms (int): The time interval to wait after sending a CONNECT request for a CONNACK to arrive.  If one does not arrive, the connection will be shut down.
        ack_timeout_sec (int): The time interval to wait for an ack after sending a QoS 1+ PUBLISH, SUBSCRIBE, or UNSUBSCRIBE before failing the operation.
        on_publish_callback_fn (Callable[[PublishReceivedData],]): Callback for all publish packets received by client.
        on_lifecycle_event_stopped_fn (Callable[[LifecycleStoppedData],]): Callback for Lifecycle Event Stopped.
        on_lifecycle_event_attempting_connect_fn (Callable[[LifecycleAttemptingConnectData],]): Callback for Lifecycle Event Attempting Connect.
        on_lifecycle_event_connection_success_fn (Callable[[LifecycleConnectSuccessData],]): Callback for Lifecycle Event Connection Success.
        on_lifecycle_event_connection_failure_fn (Callable[[LifecycleConnectFailureData],]): Callback for Lifecycle Event Connection Failure.
        on_lifecycle_event_disconnection_fn (Callable[[LifecycleDisconnectData],]): Callback for Lifecycle Event Disconnection.
    """
    host_name: str
    port: int = None
    bootstrap: ClientBootstrap = None
    socket_options: SocketOptions = None
    tls_ctx: ClientTlsContext = None
    http_proxy_options: HttpProxyOptions = None
    websocket_handshake_transform: Callable[[WebsocketHandshakeTransformArgs], None] = None
    connect_options: ConnectPacket = None
    session_behavior: ClientSessionBehaviorType = None
    extended_validation_and_flow_control_options: ExtendedValidationAndFlowControlOptions = None
    offline_queue_behavior: ClientOperationQueueBehaviorType = None
    retry_jitter_mode: ExponentialBackoffJitterMode = None
    min_reconnect_delay_ms: int = None
    max_reconnect_delay_ms: int = None
    min_connected_time_to_reset_reconnect_delay_ms: int = None
    ping_timeout_ms: int = None
    connack_timeout_ms: int = None
    ack_timeout_sec: int = None
    on_publish_callback_fn: Callable[[PublishReceivedData], None] = None
    on_lifecycle_event_stopped_fn: Callable[[LifecycleStoppedData], None] = None
    on_lifecycle_event_attempting_connect_fn: Callable[[LifecycleAttemptingConnectData], None] = None
    on_lifecycle_event_connection_success_fn: Callable[[LifecycleConnectSuccessData], None] = None
    on_lifecycle_event_connection_failure_fn: Callable[[LifecycleConnectFailureData], None] = None
    on_lifecycle_event_disconnection_fn: Callable[[LifecycleDisconnectData], None] = None


def _check_callback(callback):
    if callback is not None:
        try:
            callback_sig = signature(callback)
            callback_sig.bind(None)
            return callback
        except BaseException:
            raise TypeError(
                "Callable should take one argument")

    return None


class _ClientCore:

    def __init__(self, client_options: ClientOptions):
        self._ws_handshake_transform_cb = _check_callback(client_options.websocket_handshake_transform)
        self._on_publish_cb = _check_callback(client_options.on_publish_callback_fn)
        self._on_lifecycle_stopped_cb = _check_callback(client_options.on_lifecycle_event_stopped_fn)
        self._on_lifecycle_attempting_connect_cb = _check_callback(
            client_options.on_lifecycle_event_attempting_connect_fn)
        self._on_lifecycle_connection_success_cb = _check_callback(
            client_options.on_lifecycle_event_connection_success_fn)
        self._on_lifecycle_connection_failure_cb = _check_callback(
            client_options.on_lifecycle_event_connection_failure_fn)
        self._on_lifecycle_disconnection_cb = _check_callback(client_options.on_lifecycle_event_disconnection_fn)

    def _ws_handshake_transform(self, http_request_binding, http_headers_binding, native_userdata):
        if self._ws_handshake_transform_cb is None:
            _awscrt.mqtt5_ws_handshake_transform_complete(None, native_userdata)
            return

        def _on_complete(f):
            _awscrt.mqtt5_ws_handshake_transform_complete(f.exception(), native_userdata)

        future = Future()
        future.add_done_callback(_on_complete)

        try:
            http_request = HttpRequest._from_bindings(http_request_binding, http_headers_binding)
            transform_args = WebsocketHandshakeTransformArgs(self, http_request, future)
            self._ws_handshake_transform_cb(transform_args=transform_args)
        except Exception as e:
            # Call set_done() if user failed to do so before uncaught exception was raised,
            # there's a chance the callback wasn't callable and user has no idea we tried to hand them the baton.
            if not future.done():
                transform_args.set_done(e)

    def _on_publish(
            self,
            payload,
            qos,
            retain,
            topic,
            payload_format_indicator_exists,
            payload_format_indicator,
            message_expiry_interval_sec_exists,
            message_expiry_interval_sec,
            topic_alias_exists,
            topic_alias,
            response_topic,
            correlation_data,
            subscription_identifiers_tuples,
            content_type,
            user_properties_tuples):
        if self._on_publish_cb is None:
            return

        publish_packet = PublishPacket()
        publish_packet.topic = topic
        publish_packet.payload = payload
        publish_packet.qos = _try_qos(qos)
        publish_packet.retain = retain

        if payload_format_indicator_exists:
            publish_packet.payload_format_indicator = payload_format_indicator
        if message_expiry_interval_sec_exists:
            publish_packet.message_expiry_interval_sec = message_expiry_interval_sec
        if topic_alias_exists:
            publish_packet.topic_alias = topic_alias
        publish_packet.response_topic = response_topic
        publish_packet.correlation_data = correlation_data
        if publish_packet.subscription_identifiers is not None:
            publish_packet.subscription_identifiers = [subscription_identifier
                                                       for (subscription_identifier) in subscription_identifiers_tuples]
        publish_packet.content_type = content_type
        publish_packet.user_properties = _init_user_properties(user_properties_tuples)

        self._on_publish_cb(PublishReceivedData(publish_packet=publish_packet))

        return

    def _on_lifecycle_stopped(self):
        if self._on_lifecycle_stopped_cb:
            self._on_lifecycle_stopped_cb(LifecycleStoppedData())

    def _on_lifecycle_attempting_connect(self):
        if self._on_lifecycle_attempting_connect_cb:
            self._on_lifecycle_attempting_connect_cb(LifecycleAttemptingConnectData())

    def _on_lifecycle_connection_success(
            self,
            connack_session_present,
            connack_reason_code,
            connack_session_expiry_interval_sec_exists,
            connack_session_expiry_interval_sec,
            connack_receive_maximum_exists,
            connack_receive_maximum,
            connack_maximum_qos_exists,
            connack_maximum_qos,
            connack_retain_available_exists,
            connack_retain_available,
            connack_maximum_packet_size_exists,
            connack_maximum_packet_size,
            connack_assigned_client_identifier,
            connack_reason_string,
            connack_user_properties_tuples,
            connack_wildcard_subscriptions_available_exist,
            connack_wildcard_subscriptions_available,
            connack_subscription_identifiers_available_exists,
            connack_subscription_identifiers_available,
            connack_shared_subscriptions_available_exists,
            connack_shared_subscriptions_available,
            connack_server_keep_alive_exists,
            connack_server_keep_alive,
            connack_response_information,
            connack_server_reference,
            settings_maximum_qos,
            settings_session_expiry_interval_sec,
            settings_receive_maximum_from_server,
            settings_maximum_packet_size_to_server,
            settings_topic_alias_maximum_to_server,
            settings_topic_alias_maximum_to_client,
            settings_server_keep_alive,
            settings_retain_available,
            settings_wildcard_subscriptions_available,
            settings_subscription_identifiers_available,
            settings_shared_subscriptions_available,
            settings_rejoined_session):
        if self._on_lifecycle_connection_success_cb is None:
            return

        connack_packet = ConnackPacket()
        connack_packet.session_present = connack_session_present
        connack_packet.reason_code = _try_connect_reason_code(connack_reason_code)
        if connack_session_expiry_interval_sec_exists:
            connack_packet.session_expiry_interval_sec = connack_session_expiry_interval_sec
        if connack_receive_maximum_exists:
            connack_packet.receive_maximum = connack_receive_maximum
        if connack_maximum_qos_exists:
            connack_packet.maximum_qos = _try_qos(connack_maximum_qos)
        if connack_retain_available_exists:
            connack_packet.retain_available = connack_retain_available
        if connack_maximum_packet_size_exists:
            connack_packet.maximum_packet_size = connack_maximum_packet_size
        connack_packet.assigned_client_identifier = connack_assigned_client_identifier
        connack_packet.reason_string = connack_reason_string
        connack_packet.user_properties = _init_user_properties(connack_user_properties_tuples)
        if connack_wildcard_subscriptions_available_exist:
            connack_packet.wildcard_subscriptions_available = connack_wildcard_subscriptions_available
        if connack_subscription_identifiers_available_exists:
            connack_packet.subscription_identifiers_available = connack_subscription_identifiers_available
        if connack_shared_subscriptions_available_exists:
            connack_packet.shared_subscription_available = connack_shared_subscriptions_available
        if connack_server_keep_alive_exists:
            connack_packet.server_keep_alive = connack_server_keep_alive
        connack_packet.response_information = connack_response_information
        connack_packet.server_reference = connack_server_reference

        negotiated_settings = NegotiatedSettings()
        negotiated_settings.maximum_qos = _try_qos(settings_maximum_qos)
        negotiated_settings.session_expiry_interval_sec = settings_session_expiry_interval_sec
        negotiated_settings.receive_maximum_from_server = settings_receive_maximum_from_server
        negotiated_settings.maximum_packet_size_to_server = settings_maximum_packet_size_to_server
        negotiated_settings.topic_alias_maximum_to_server = settings_topic_alias_maximum_to_server
        negotiated_settings.topic_alias_maximum_to_client = settings_topic_alias_maximum_to_client
        negotiated_settings.server_keep_alive_sec = settings_server_keep_alive
        negotiated_settings.retain_available = settings_retain_available
        negotiated_settings.wildcard_subscriptions_available = settings_wildcard_subscriptions_available
        negotiated_settings.subscription_identifiers_available = settings_subscription_identifiers_available
        negotiated_settings.shared_subscriptions_available = settings_shared_subscriptions_available
        negotiated_settings.rejoined_session = settings_rejoined_session

        self._on_lifecycle_connection_success_cb(
            LifecycleConnectSuccessData(
                connack_packet=connack_packet,
                negotiated_settings=negotiated_settings))

    def _on_lifecycle_connection_failure(
            self,
            error_code,
            connack_packet_exists,
            connack_session_present,
            connack_reason_code,
            connack_session_expiry_interval_exists,
            connack_session_expiry_interval_sec,
            connack_receive_maximum_exists,
            connack_receive_maximum,
            connack_maximum_qos_exists,
            connack_maximum_qos,
            connack_retain_available_exists,
            connack_retain_available,
            connack_maximum_packet_size_exists,
            connack_maximum_packet_size,
            connack_assigned_client_identifier,
            connack_reason_string,
            connack_user_properties_tuples,
            connack_wildcard_subscriptions_available_exist,
            connack_wildcard_subscriptions_available,
            connack_subscription_identifiers_available_exists,
            connack_subscription_identifiers_available,
            connack_shared_subscriptions_available_exists,
            connack_shared_subscriptions_available,
            connack_server_keep_alive_exists,
            connack_server_keep_alive,
            connack_response_information,
            connack_server_reference):
        if self._on_lifecycle_connection_failure_cb is None:
            return

        if connack_packet_exists:
            connack_packet = ConnackPacket()
            connack_packet.session_present = connack_session_present
            connack_packet.reason_code = _try_connect_reason_code(connack_reason_code)
            if connack_session_expiry_interval_exists:
                connack_packet.session_expiry_interval_sec = connack_session_expiry_interval_sec
            if connack_receive_maximum_exists:
                connack_packet.receive_maximum = connack_receive_maximum
            if connack_maximum_qos_exists:
                connack_packet.maximum_qos = _try_qos(connack_maximum_qos)
            if connack_retain_available_exists:
                connack_packet.retain_available = connack_retain_available
            if connack_maximum_packet_size_exists:
                connack_packet.maximum_packet_size = connack_maximum_packet_size
            connack_packet.assigned_client_identifier = connack_assigned_client_identifier
            connack_packet.reason_string = connack_reason_string
            connack_packet.user_properties = _init_user_properties(connack_user_properties_tuples)
            if connack_wildcard_subscriptions_available_exist:
                connack_packet.wildcard_subscriptions_available = connack_wildcard_subscriptions_available
            if connack_subscription_identifiers_available_exists:
                connack_packet.subscription_identifiers_available = connack_subscription_identifiers_available
            if connack_shared_subscriptions_available_exists:
                connack_packet.shared_subscription_available = connack_shared_subscriptions_available
            if connack_server_keep_alive_exists:
                connack_packet.server_keep_alive = connack_server_keep_alive
            connack_packet.response_information = connack_response_information
            connack_packet.server_reference = connack_server_reference

            self._on_lifecycle_connection_failure_cb(
                LifecycleConnectFailureData(
                    connack_packet=connack_packet,
                    exception=exceptions.from_code(error_code)))
        else:
            self._on_lifecycle_connection_failure_cb(
                LifecycleConnectFailureData(
                    connack_packet=None, exception=exceptions.from_code(error_code)))

    def _on_lifecycle_disconnection(
            self,
            error_code,
            disconnect_packet_exists,
            reason_code,
            session_expiry_interval_sec_exists,
            session_expiry_interval_sec,
            reason_string,
            user_properties_tuples,
            server_reference):
        if self._on_lifecycle_disconnection_cb is None:
            return

        if disconnect_packet_exists:
            disconnect_packet = DisconnectPacket()
            disconnect_packet.reason_code = _try_disconnect_reason_code(reason_code)
            if session_expiry_interval_sec_exists:
                disconnect_packet.session_expiry_interval_sec = session_expiry_interval_sec
            disconnect_packet.reason_string = reason_string
            disconnect_packet.user_properties = _init_user_properties(user_properties_tuples)
            disconnect_packet.server_reference = server_reference
            self._on_lifecycle_disconnection_cb(
                LifecycleDisconnectData(
                    disconnect_packet=disconnect_packet,
                    exception=exceptions.from_code(error_code)))
        else:
            self._on_lifecycle_disconnection_cb(
                LifecycleDisconnectData(
                    disconnect_packet=None,
                    exception=exceptions.from_code(error_code)))


class Client(NativeResource):
    """This class wraps the aws-c-mqtt MQTT5 client to provide the basic MQTT5 pub/sub functionalities via the AWS Common Runtime

    One Client class creates one connection.

    Args:
        client_options (ClientOptions): The ClientOptions dataclass to used to configure the new Client.

    """

    def __init__(self, client_options: ClientOptions):

        super().__init__()

        core = _ClientCore(client_options)

        bootstrap = client_options.bootstrap

        if not bootstrap:
            bootstrap = ClientBootstrap.get_or_create_static_default()

        connect_options = client_options.connect_options
        if not connect_options:
            connect_options = ConnectPacket()

        socket_options = client_options.socket_options
        if not socket_options:
            socket_options = SocketOptions()

        if not connect_options.will:
            is_will_none = True
            will = PublishPacket()
        else:
            is_will_none = False
            will = connect_options.will

        websocket_is_none = client_options.websocket_handshake_transform is None

        self._binding = _awscrt.mqtt5_client_new(self,
                                                 client_options.host_name,
                                                 client_options.port,
                                                 bootstrap,
                                                 socket_options,
                                                 client_options.tls_ctx,
                                                 client_options.http_proxy_options,
                                                 connect_options.client_id,
                                                 connect_options.keep_alive_interval_sec,
                                                 connect_options.username,
                                                 connect_options.password,
                                                 connect_options.session_expiry_interval_sec,
                                                 connect_options.request_response_information,
                                                 connect_options.request_problem_information,
                                                 connect_options.receive_maximum,
                                                 connect_options.maximum_packet_size,
                                                 connect_options.will_delay_interval_sec,
                                                 connect_options.user_properties,
                                                 is_will_none,
                                                 will.qos,
                                                 will.payload,
                                                 will.retain,
                                                 will.topic,
                                                 will.payload_format_indicator,
                                                 will.message_expiry_interval_sec,
                                                 will.topic_alias,
                                                 will.response_topic,
                                                 will.correlation_data,
                                                 will.content_type,
                                                 will.user_properties,
                                                 client_options.session_behavior,
                                                 client_options.extended_validation_and_flow_control_options,
                                                 client_options.offline_queue_behavior,
                                                 client_options.retry_jitter_mode,
                                                 client_options.min_reconnect_delay_ms,
                                                 client_options.max_reconnect_delay_ms,
                                                 client_options.min_connected_time_to_reset_reconnect_delay_ms,
                                                 client_options.ping_timeout_ms,
                                                 client_options.ack_timeout_sec,
                                                 websocket_is_none,
                                                 core)

    def start(self):
        """Notifies the MQTT5 client that you want it maintain connectivity to the configured endpoint.
        The client will attempt to stay connected using the properties of the reconnect-related parameters in the mqtt5 client configuration.

        This is an asynchronous operation."""
        _awscrt.mqtt5_client_start(self._binding)

    def stop(self, disconnect_packet: DisconnectPacket = None):
        """Notifies the MQTT5 client that you want it to end connectivity to the configured endpoint, disconnecting any existing connection and halting any reconnect attempts.

        This is an asynchronous operation.

        Args:
            disconnect_packet (DisconnectPacket): (optional) Properties of a DISCONNECT packet to send as part of the shutdown process
        """
        is_disconnect_packet_none = disconnect_packet is None

        if is_disconnect_packet_none:
            disconnect_packet = DisconnectPacket()

        _awscrt.mqtt5_client_stop(self._binding,
                                  is_disconnect_packet_none,
                                  disconnect_packet.reason_code,
                                  disconnect_packet.session_expiry_interval_sec,
                                  disconnect_packet.reason_string,
                                  disconnect_packet.user_properties,
                                  disconnect_packet.server_reference)

    def publish(self, publish_packet: PublishPacket):
        """Tells the client to attempt to send a PUBLISH packet.

        Will return a future containing a PubAckResult if the publish is successful. The data in the PubAckResult varies depending on the QoS of the Publish. For QoS 0, the PubAckResult will not contain data. For QoS 1, the PubAckResult will contain a PubAckPacket. See PubAckResult class documentation for more info.

        Args:
            publish_packet (PublishPacket): PUBLISH packet to send to the server

        Returns:
            A future with a (:class:`PublishCompletionData`)
        """

        future = Future()

        # TODO QoS 2 Pubcomp will be handled through the same callback in the future
        def puback(error_code, qos, reason_code, reason_string, user_properties_tuples):
            publish_completion_data = PublishCompletionData()
            puback_packet = PubackPacket()
            publish_completion_data.puback = puback_packet

            if error_code != 0:
                future.set_exception(exceptions.from_code(error_code))
            else:
                if qos == 1:
                    puback_packet.reason_code = _try_puback_reason_code(reason_code)
                    puback_packet.reason_string = reason_string
                    puback_packet.user_properties = _init_user_properties(user_properties_tuples)

                future.set_result(publish_completion_data)

        _awscrt.mqtt5_client_publish(self._binding,
                                     publish_packet.qos,
                                     publish_packet.payload,
                                     publish_packet.retain,
                                     publish_packet.topic,
                                     publish_packet.payload_format_indicator,
                                     publish_packet.message_expiry_interval_sec,
                                     publish_packet.topic_alias,
                                     publish_packet.response_topic,
                                     publish_packet.correlation_data,
                                     publish_packet.content_type,
                                     publish_packet.user_properties,
                                     puback)

        return future

    def subscribe(self, subscribe_packet: SubscribePacket):
        """Tells the client to attempt to subscribe to one or more topic filters.

        Args:
            subscribe_packet (SubscribePacket): SUBSCRIBE packet to send to the server

        Returns:
            A future with a (:class:`SubackPacket`)
        """

        future = Future()

        def suback(error_code, reason_codes, reason_string, user_properties_tuples):
            suback_packet = SubackPacket()
            if error_code != 0:
                future.set_exception(exceptions.from_code(error_code))
            else:
                suback_packet.reason_codes = [_try_suback_reason_code(reason_code) for (reason_code) in reason_codes]
                suback_packet.reason_string = reason_string
                suback_packet.user_properties = _init_user_properties(user_properties_tuples)
                future.set_result(suback_packet)

        _awscrt.mqtt5_client_subscribe(self._binding,
                                       subscribe_packet.subscriptions,
                                       subscribe_packet.subscription_identifier,
                                       subscribe_packet.user_properties,
                                       suback)

        return future

    def unsubscribe(self, unsubscribe_packet: UnsubscribePacket):
        """Tells the client to attempt to unsubscribe from one or more topic filters.

        Args:
            unsubscribe_packet (UnsubscribePacket): UNSUBSCRIBE packet to send to the server

        Returns:
            A future with a (:class:`UnsubackPacket`)
        """

        future = Future()

        def unsuback(error_code, reason_codes, reason_string, user_properties_tuples):
            unsuback_packet = UnsubackPacket()
            if error_code != 0:
                future.set_exception(exceptions.from_code(error_code))
            else:
                unsuback_packet.reason_codes = [_try_unsuback_reason_code(
                    reason_code) for (reason_code) in reason_codes]
                unsuback_packet.reason_string = reason_string
                unsuback_packet.user_properties = _init_user_properties(user_properties_tuples)
                future.set_result(unsuback_packet)

        _awscrt.mqtt5_client_unsubscribe(self._binding,
                                         unsubscribe_packet.topic_filters,
                                         unsubscribe_packet.user_properties,
                                         unsuback)

        return future

    def get_stats(self):
        """Queries the client's internal statistics for incomplete operations.

        Returns:
            A future with a (:class:`OperationStatisticsData`)
        """

        future = Future()

        def get_stats_result(
                incomplete_operation_count,
                incomplete_operation_size,
                unacked_operation_count,
                unacked_operation_size):
            operation_statistics_data = OperationStatisticsData(
                incomplete_operation_count,
                incomplete_operation_size,
                unacked_operation_count,
                unacked_operation_size)
            future.set_result(operation_statistics_data)

        _awscrt.mqtt5_client_get_stats(self._binding, get_stats_result)

        return future
