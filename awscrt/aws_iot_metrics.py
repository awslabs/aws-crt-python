# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import sys


@dataclass
class IoTMetricsMetadata:
    """A key-value pair for IoT SDK metrics metadata.

    Metadata entries are appended to the MQTT CONNECT packet username field
    as part of the Metadata query parameter.

    Args:
        key (str): The metadata key (e.g., "IoTSDKVersion", "IoTSDKFeature", "CRTVersion")
        value (str): The metadata value
    """
    key: str
    value: str


@dataclass
class AWSIoTMetrics:
    """Configuration for IoT SDK metrics that are embedded in MQTT Connect Packet username field.

    Args:
        library_name (str): The SDK library name (e.g., "IoTDeviceSDK/Python")
        metadata_entries (Optional[List[IoTMetricsMetadata]]): Optional list for storing key-value pairs of metadata

    """
    library_name: str = "IoTDeviceSDK/Python"
    metadata_entries: Optional[List[IoTMetricsMetadata]] = None


# Metrics Version Constant
IOT_SDK_METRICS_FEATURE_VERSION = 1

# Feature ID Constants


class _MetricsFeatureId(str, Enum):
    """Feature IDs for IoT SDK metrics tracking.

    Each ID is a single character used to encode feature usage in the metrics
    string with the format "ID/Value". IDs are assigned sequentially and never
    reused to ensure historical data consistency across SDK versions.
    """
    RETRY_JITTER_MODE = "A"
    SESSION_BEHAVIOR = "B"
    OFFLINE_QUEUE_BEHAVIOR = "C"
    OUTBOUND_TOPIC_ALIAS_BEHAVIOR = "D"
    INBOUND_TOPIC_ALIAS_BEHAVIOR = "E"
    PROTOCOL_VERSION = "F"
    SOCKET_IMPLEMENTATION = "G"
    HTTP_PROXY_TYPE = "H"
    CERTIFICATE_SOURCE = "I"
    TLS_CIPHER_PREFERENCE = "J"
    MINIMUM_TLS_VERSION = "K"

# Feature Value Constants


class _MetricsProtocolVersionValue(str, Enum):
    """Protocol version values for metrics encoding.

    Maps MQTT protocol versions to their single-character metric representations.
    """
    MQTT311 = "3"
    MQTT5 = "5"


class _MetricsSocketImplementationValue(str, Enum):
    """Socket implementation values for metrics encoding.

    Maps the underlying platform socket layer to its metric representation.
    POSIX covers macOS and Linux; WINSOCK covers Windows.
    """
    POSIX = "A"
    WINSOCK = "B"


class _MetricsHttpProxyTypeValue(str, Enum):
    """HTTP proxy type values for metrics encoding.

    Indicates whether the proxy connection uses plain HTTP or HTTPS (TLS).
    """
    HTTP = "A"
    HTTPS = "B"

# Mappings from existing enums to metrics values


def _retry_jitter_metrics_value(mode):
    """Map ExponentialBackoffJitterMode to its single-character metrics value.

    Mapping: NONE->A, FULL->B, DECORRELATED->C.
    Returns None for DEFAULT.
    """
    from awscrt.mqtt5 import ExponentialBackoffJitterMode
    mapping = {
        ExponentialBackoffJitterMode.NONE: "A",
        ExponentialBackoffJitterMode.FULL: "B",
        ExponentialBackoffJitterMode.DECORRELATED: "C",
    }
    return mapping.get(mode)


def _client_session_behavior_metrics_value(behavior):
    """Map ClientSessionBehaviorType to its single-character metrics value.

    Mapping: CLEAN->A, REJOIN_POST_SUCCESS->B, REJOIN_ALWAYS->C.
    Returns None for DEFAULT.
    """
    from awscrt.mqtt5 import ClientSessionBehaviorType
    mapping = {
        ClientSessionBehaviorType.CLEAN: "A",
        ClientSessionBehaviorType.REJOIN_POST_SUCCESS: "B",
        ClientSessionBehaviorType.REJOIN_ALWAYS: "C",
    }
    return mapping.get(behavior)


def _client_operation_queue_behavior_metrics_value(behavior):
    """Map ClientOperationQueueBehaviorType to its single-character metrics value.

    Mapping: FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT->A,
    FAIL_QOS0_PUBLISH_ON_DISCONNECT->B, FAIL_ALL_ON_DISCONNECT->C.
    Returns None for DEFAULT.
    """
    from awscrt.mqtt5 import ClientOperationQueueBehaviorType
    mapping = {
        ClientOperationQueueBehaviorType.FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT: "A",
        ClientOperationQueueBehaviorType.FAIL_QOS0_PUBLISH_ON_DISCONNECT: "B",
        ClientOperationQueueBehaviorType.FAIL_ALL_ON_DISCONNECT: "C",
    }
    return mapping.get(behavior)


def _outbound_topic_alias_behavior_metrics_value(behavior):
    """Map OutboundTopicAliasBehaviorType to its single-character metrics value.

    Mapping: MANUAL->A, LRU->B, DISABLED->C.
    Returns None for DEFAULT.
    """
    from awscrt.mqtt5 import OutboundTopicAliasBehaviorType
    mapping = {
        OutboundTopicAliasBehaviorType.MANUAL: "A",
        OutboundTopicAliasBehaviorType.LRU: "B",
        OutboundTopicAliasBehaviorType.DISABLED: "C",
    }
    return mapping.get(behavior)


def _inbound_topic_alias_behavior_metrics_value(behavior):
    """Map InboundTopicAliasBehaviorType to its single-character metrics value.

    Mapping: ENABLED->A, DISABLED->B.
    Returns None for DEFAULT.
    """
    from awscrt.mqtt5 import InboundTopicAliasBehaviorType
    mapping = {
        InboundTopicAliasBehaviorType.ENABLED: "A",
        InboundTopicAliasBehaviorType.DISABLED: "B",
    }
    return mapping.get(behavior)


def _minimum_tls_version_metrics_value(version):
    """Map TlsVersion to its single-character metrics value.

    Mapping: SSLv3->A, TLSv1->B, TLSv1_1->C, TLSv1_2->D, TLSv1_3->E.
    Returns None for DEFAULT.
    """
    from awscrt.io import TlsVersion
    mapping = {
        TlsVersion.SSLv3: "A",
        TlsVersion.TLSv1: "B",
        TlsVersion.TLSv1_1: "C",
        TlsVersion.TLSv1_2: "D",
        TlsVersion.TLSv1_3: "E",
    }
    return mapping.get(version)


def _tls_cipher_preference_metrics_value(pref):
    """Map TlsCipherPref to its single-character metrics value.

    Mapping: PQ_TLSv1_0_2021_05->A, PQ_DEFAULT->B, TLSv1_2_2025_07->C.
    Returns None for DEFAULT.
    """
    from awscrt.io import TlsCipherPref
    mapping = {
        TlsCipherPref.PQ_TLSv1_0_2021_05: "A",
        TlsCipherPref.PQ_DEFAULT: "B",
        TlsCipherPref.TLSv1_2_2025_07: "C",
    }
    return mapping.get(pref)


def _detect_socket_implementation():
    """Detect the socket implementation based on the current platform.

    Returns _MetricsSocketImplementationValue.WINSOCK on Windows,
    _MetricsSocketImplementationValue.POSIX on all other platforms
    (macOS, Linux).
    """
    if sys.platform == "win32":
        return _MetricsSocketImplementationValue.WINSOCK
    return _MetricsSocketImplementationValue.POSIX


# MQTT5 encoding list
def _get_encoded_feature_list(client_options):
    """Generates the encoded feature list string for metrics from MQTT5 ClientOptions.

    Format: "ID/Value,ID/Value,..."
    Example: "A/B,C/A,F/5,G/A" means retry_jitter_mode=FULL, offline_queue_behavior=
    FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT, protocol=MQTT5, socket=POSIX.

    MQTT5 connections always include:
        - F (protocol_version): set to MQTT5
        - G (socket_implementation): detected from platform (POSIX or WINSOCK)

    Conditionally includes (only when the option is explicitly set and not DEFAULT):
        - A (retry_jitter_mode): from client_options.retry_jitter_mode
        - B (session_behavior): from client_options.session_behavior
        - C (offline_queue_behavior): from client_options.offline_queue_behavior
        - D (outbound_topic_alias_behavior): from topic_aliasing_options.outbound_behavior
        - E (inbound_topic_alias_behavior): from topic_aliasing_options.inbound_behavior
        - H (http_proxy_type): HTTP or HTTPS based on proxy TLS settings
        - J (tls_cipher_preference): mapped from TlsCipherPref on the TLS context
        - K (minimum_tls_version): mapped from TlsVersion on the TLS context

    Feature I (certificate_source) is set at the IoT SDK level, not here.

    Args:
        client_options: MQTT5 ClientOptions dataclass.
    Returns:
        str: The encoded feature list string.
    """

    features = []

    # A: retry_jitter_mode
    if client_options.retry_jitter_mode is not None:
        val = _retry_jitter_metrics_value(client_options.retry_jitter_mode)
        if val:
            features.append(f"{_MetricsFeatureId.RETRY_JITTER_MODE.value}/{val}")

    # B: session_behavior
    if client_options.session_behavior is not None:
        val = _client_session_behavior_metrics_value(client_options.session_behavior)
        if val:
            features.append(f"{_MetricsFeatureId.SESSION_BEHAVIOR.value}/{val}")

    # C: offline_queue_behavior
    if client_options.offline_queue_behavior is not None:
        val = _client_operation_queue_behavior_metrics_value(client_options.offline_queue_behavior)
        if val:
            features.append(f"{_MetricsFeatureId.OFFLINE_QUEUE_BEHAVIOR.value}/{val}")

    # D: outbound_topic_alias_behavior
    if client_options.topic_aliasing_options is not None:
        if client_options.topic_aliasing_options.outbound_behavior is not None:
            val = _outbound_topic_alias_behavior_metrics_value(client_options.topic_aliasing_options.outbound_behavior)
            if val:
                features.append(f"{_MetricsFeatureId.OUTBOUND_TOPIC_ALIAS_BEHAVIOR.value}/{val}")

    # E: inbound_topic_alias_behavior
    if client_options.topic_aliasing_options is not None:
        if client_options.topic_aliasing_options.inbound_behavior is not None:
            val = _inbound_topic_alias_behavior_metrics_value(client_options.topic_aliasing_options.inbound_behavior)
            if val:
                features.append(f"{_MetricsFeatureId.INBOUND_TOPIC_ALIAS_BEHAVIOR.value}/{val}")

    # F: protocol_version - MQTT5 always uses client options
    features.append(f"{_MetricsFeatureId.PROTOCOL_VERSION.value}/{_MetricsProtocolVersionValue.MQTT5.value}")

    # G: socket_implementation - Detect based on platform
    features.append(f"{_MetricsFeatureId.SOCKET_IMPLEMENTATION.value}/{_detect_socket_implementation().value}")

    # H: http_proxy_type - Determine based on whether proxy uses TLS
    if client_options.http_proxy_options is not None:
        proxy_type = _MetricsHttpProxyTypeValue.HTTPS if getattr(
            client_options.http_proxy_options,
            'tls_connection_options',
            None) is not None else _MetricsHttpProxyTypeValue.HTTP
        features.append(f"{_MetricsFeatureId.HTTP_PROXY_TYPE.value}/{proxy_type.value}")

    # I: certificate_source - Would need to be tracked from TLS context setup. This is set at a IoT SDK level

    # J: tls_cipher_preference - security policy
    if client_options.tls_ctx is not None:
        val = _tls_cipher_preference_metrics_value(client_options.tls_ctx._cipher_pref)
        if val:
            features.append(f"{_MetricsFeatureId.TLS_CIPHER_PREFERENCE.value}/{val}")

    # K: minimum_tls_version - The minimum TLS version set on TLSContextOptions
    if client_options.tls_ctx is not None:
        val = _minimum_tls_version_metrics_value(client_options.tls_ctx._min_tls_ver)
        if val:
            features.append(f"{_MetricsFeatureId.MINIMUM_TLS_VERSION.value}/{val}")

    return ",".join(features)

# MQTT3 encoding list


def _get_encoded_feature_list_mqtt3(proxy_options, tls_ctx=None):
    """Generates the encoded feature list string for metrics from MQTT3 connection options.
    Format: "ID/Value,ID/Value..."

    MQTT3 connections always include:
        - F (protocol_version): set to MQTT311
        - G (socket_implementation): detected from platform (POSIX or WINSOCK)

    Conditionally includes:
        - H (http_proxy_type): HTTP or HTTPS based on proxy TLS settings
        - J (tls_cipher_preference): mapped from TlsCipherPref on the TLS context
        - K (minimum_tls_version): mapped from TlsVersion on the TLS context

    Args:
        proxy_options: Optional HttpProxyOptions from the Connection.
        tls_ctx: Optional ClientTlsContext used by the connection.
    Returns:
        str: The encoded feature list string.
    """
    features = [
        f"{_MetricsFeatureId.PROTOCOL_VERSION.value}/{_MetricsProtocolVersionValue.MQTT311.value}",
        f"{_MetricsFeatureId.SOCKET_IMPLEMENTATION.value}/{_detect_socket_implementation().value}"
    ]
    # H: http_proxy_type - Determine based on whether proxy uses TLS
    if proxy_options is not None:
        proxy_type = _MetricsHttpProxyTypeValue.HTTPS if getattr(
            proxy_options, 'tls_connection_options', None) is not None else _MetricsHttpProxyTypeValue.HTTP
        features.append(f"{_MetricsFeatureId.HTTP_PROXY_TYPE.value}/{proxy_type.value}")

    # J: tls_cipher_preference - security policy
    if tls_ctx is not None:
        val = _tls_cipher_preference_metrics_value(tls_ctx._cipher_pref)
        if val:
            features.append(f"{_MetricsFeatureId.TLS_CIPHER_PREFERENCE.value}/{val}")

    # K: minimum_tls_version - the minimum TLS version set on TLSContextOptions
    if tls_ctx is not None:
        val = _minimum_tls_version_metrics_value(tls_ctx._min_tls_ver)
        if val:
            features.append(f"{_MetricsFeatureId.MINIMUM_TLS_VERSION.value}/{val}")

    return ",".join(features)


def _merge_feature_lists(crt_features, user_features):
    """Merge CRT-generated features with user-provided (IoT SDK) features.

    When both lists contain the same feature ID, the user-provided value
    takes precedence.

    Args:
        crt_features (str): CRT-generated feature list.
        user_features (str): User-provided feature list from the IoT SDK.
            May be empty string if no SDK features are provided.
    Returns:
        str: The merged feature list string.
    """
    merged = {}
    # Parse CRT Features
    for pair in crt_features.split(","):
        if "/" in pair:
            fid, val = pair.split("/", 1)
            merged[fid] = val

    for pair in user_features.split(","):
        if "/" in pair:
            fid, val = pair.split("/", 1)
            merged[fid] = val
    return ",".join(f"{k}/{v}" for k, v in merged.items())

# Metrics creation


def _create_metrics(user_metrics, crt_feature_list):
    """Create the final AWSIoTMetrics object by merging CRT and user-provided data.

    Applies the following rules to produce the final metrics:

    1. library_name: Uses the value from user_metrics if provided,
       otherwise defaults to "IoTDeviceSDK/Python".
    2. CRTVersion: Automatically set to the current awscrt
       package version. Cannot be overridden by user input.
    3. IoTSDKMetricsVersion: Always set to the current
       IOT_SDK_METRICS_FEATURE_VERSION constant.
    4. IoTSDKFeature: If the user-provided metrics version
       matches IOT_SDK_METRICS_FEATURE_VERSION, the CRT feature list is
       merged with the user's IoTSDKFeature (user values take precedence
       for duplicate feature IDs). Otherwise, only CRT features are used.
    5. Any additional user metadata entries (other than CRTVersion,
       IoTSDKMetricsVersion, IoTSDKFeature) are passed through unchanged.

    Args:
        user_metrics : Metrics configuration from
            the IoT SDK. May be None if no SDK-level metrics are provided.
        crt_feature_list : Encoded CRT feature list string generated
            by _get_encoded_feature_list or _get_encoded_feature_list_mqtt3.
    Returns:
        AWSIoTMetrics: The final metrics object ready to be embedded in the
            MQTT CONNECT packet username field.
    """

    from awscrt import __version__ as crt_version

    final_metrics = AWSIoTMetrics(
        library_name=user_metrics.library_name if user_metrics else "IoTDeviceSDK/Python"
    )

    # CRTVERSION: not modifiable by user, automatically set
    metadata = {"CRTVersion": crt_version}

    # Extract user_metadata from IoT SDK
    user_metrics_version = None
    user_feature = ""
    if user_metrics and user_metrics.metadata_entries:
        for entry in user_metrics.metadata_entries:
            if entry.key == "IoTSDKMetricsVersion":
                user_metrics_version = entry.value
            elif entry.key == "IoTSDKFeature":
                user_feature = entry.value
            elif entry.key != "CRTVersion":
                metadata[entry.key] = entry.value

    # Merge features: if version matches, merge CRT + SDK; otherwise CRT only
    if (user_metrics_version is not None and user_metrics_version.isdigit() and int(
            user_metrics_version) == IOT_SDK_METRICS_FEATURE_VERSION):
        metadata["IoTSDKFeature"] = _merge_feature_lists(crt_feature_list, user_feature)
    else:
        metadata["IoTSDKFeature"] = _merge_feature_lists(crt_feature_list, "")

    # Always set current metrics version
    metadata["IoTSDKMetricsVersion"] = str(IOT_SDK_METRICS_FEATURE_VERSION)

    final_metrics.metadata_entries = [IoTMetricsMetadata(key=k, value=v) for k, v in metadata.items()]
    return final_metrics


def _create_metrics_mqtt5(client_options):
    """Create the final AWSIoTMetrics object for an MQTT5 client.

    Generates the CRT feature list from the full set of MQTT5 ClientOptions

    Args:
        client_options: MQTT5 ClientOptions dataclass containing all
            connection configuration and optional user metrics.
    Returns:
        AWSIoTMetrics: The final metrics object with merged CRT and SDK features.
    """
    crt_feature_list = _get_encoded_feature_list(client_options)
    return _create_metrics(client_options.metrics, crt_feature_list)


def _create_metrics_mqtt3(user_metrics=None, proxy_options=None, tls_ctx=None):
    """Creates the final AWSIoTMetrics object for an MQTT3 connection.

    Generates the CRT feature list from the MQTT3 connection parameters

    Args:
        user_metrics : Optional metrics configuration
            provided by the IoT SDK. If None, defaults are used.
        proxy_options : Optional HTTP proxy options
            from the Connection, used to determine proxy type feature.
        tls_ctx : Optional TLS context from the
            connection, used to determine cipher preference and minimum TLS
            version features.
    Returns:
        AWSIoTMetrics: The final metrics object with merged CRT and SDK features.
    """
    crt_feature_list = _get_encoded_feature_list_mqtt3(proxy_options, tls_ctx)
    return _create_metrics(user_metrics, crt_feature_list)
