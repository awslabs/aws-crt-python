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
    """
    Configuration for IoT SDK metrics that are embedded in MQTT Connect Packet username field.

    Args:
        library_name (str): The SDK library name (e.g., "IoTDeviceSDK/Python")
        metadata_entries (Optional[List[IoTMetricsMetadata]]): Optional list for storing key-value pairs of metadata

    """
    library_name: str = "IoTDeviceSDK/Python"
    metadata_entries: Optional[List[IoTMetricsMetadata]] = None

# Metrics Version Constant
IOT_SDK_METRICS_FEATURE_VERSION = 1

# Feature ID Constants
class MetricsFeatureId(str, Enum):
    """
    Feature IDs for IoT SDK metrics tracking.
    These IDs are used to encode feature usage in the metrics string. They are assigned sequentially and never reused to ensure historical data consistency
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
class MetricsProtocolVersionValue(str,Enum):
    """
    Protocol version values for metrics
    """
    MQTT311 = "3"
    MQTT5 = "5"

class MetricsSocketImplementationValue(str, Enum):
    """
    Socket implementation values for metrics
    """
    POSIX = "A"
    WINSOCK = "B"

class MetricsHttpProxyTypeValue(str, Enum):
    """
    HTTP proxy type values for metrics
    """
    HTTP = "A"
    HTTPS = "B"

# Mappings from existing enums to metrics values

def _retry_jitter_metrics_value(mode):
    """
    Map ExponentialBackoffJitterMode to metrics value.
    NONE->A, FULL->B, DECORRELATED->C, DEFAULT->None
    """
    from awscrt.mqtt5 import ExponentialBackoffJitterMode
    mapping = {
        ExponentialBackoffJitterMode.NONE: "A",
        ExponentialBackoffJitterMode.FULL: "B",
        ExponentialBackoffJitterMode.DECORRELATED: "C",
    }
    return mapping.get(mode)

def _client_session_behavior_metrics_value(behavior):
    """
    Map ClientSessionBehaviorType to metrics value.
    CLEAN->A, REJOINPOSTSUCCESS->B, REJOINALWAYS->C, DEFAULT->None
    """
    from awscrt.mqtt5 import ClientSessionBehaviorType
    mapping = {
        ClientSessionBehaviorType.CLEAN: "A",
        ClientSessionBehaviorType.REJOIN_POST_SUCCESS: "B",
        ClientSessionBehaviorType.REJOIN_ALWAYS: "C",
    }
    return mapping.get(behavior)

def _client_operation_queue_behavior_metrics_value(behavior):
    """
    Map ClientOperationQueueBehaviorType to metrics value.
    FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT->A, FAIL_QOS0_PUBLISH_ON_DISCONNECT->B,
    FAIL_ALL_ON_DISCONNECT->C, DEFAULT->None.
    """
    from awscrt.mqtt5 import ClientOperationQueueBehaviorType
    mapping = {
        ClientOperationQueueBehaviorType.FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT: "A",
        ClientOperationQueueBehaviorType.FAIL_QOS0_PUBLISH_ON_DISCONNECT: "B",
        ClientOperationQueueBehaviorType.FAIL_ALL_ON_DISCONNECT: "C",
    }
    return mapping.get(behavior)

def _outbound_topic_alias_behavior_metrics_value(behavior):
    """
    Map OutboundTopicAliasBehaviorType to metrics value.
    MANUAL->A, LRU->B, DISABLED->C, DEFAULT->None.
    """
    from awscrt.mqtt5 import OutboundTopicAliasBehaviorType
    mapping = {
        OutboundTopicAliasBehaviorType.MANUAL: "A",
        OutboundTopicAliasBehaviorType.LRU: "B",
        OutboundTopicAliasBehaviorType.DISABLED: "C",
    }
    return mapping.get(behavior)

def _inbound_topic_alias_behavior_metrics_value(behavior):
    """
    Map InboundTopicAliasBehaviorType to metrics value.
    ENABLED->A, DISABLED->B, DEFAULT->None.
    """
    from awscrt.mqtt5 import InboundTopicAliasBehaviorType
    mapping = {
        InboundTopicAliasBehaviorType.ENABLED: "A",
        InboundTopicAliasBehaviorType.DISABLED:"B",
    }
    return mapping.get(behavior)

def _minimum_tls_version_metrics_value(version):
    """
    Map TlsVersion to metrics value.
    SSLv3->A, TLSv1->B, TLSv1_1->C, TLSv1_2->D, TLSv1_3->E
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
    """Map TlsCipherPref to metrics value.
    PQ_TLSv1_0_2021_05→A, PQ_DEFAULT→B, TLSv1_2_2025_07→C, DEFAULT→None (omitted)"""
    from awscrt.io import TlsCipherPref
    mapping = {
        TlsCipherPref.PQ_TLSv1_0_2021_05: "A",
        TlsCipherPref.PQ_DEFAULT: "B",
        TlsCipherPref.TLSv1_2_2025_07: "C",
    }
    return mapping.get(pref)

def _detect_socket_implementation():
    """
    Helper function to detect socket implementation based on platform
    Python CRT is built for macOS (POSIX), Linux (POSIX), and Windows (WINSOCK).
    """
    if sys.platform == "win32":
        return MetricsSocketImplementationValue.WINSOCK
    return MetricsSocketImplementationValue.POSIX


#MQTT5 encoding list
def get_encoded_feature_list(client_options):
    """
    Generates the encoded feature list string for metrics directly from client options.
    Format: "ID/Value,ID/Value..."
    Example: "A/B,C/A" means Feature A (retry_jitter_mode) with value B (FULL),
            and Feature C (offline_queue_behavior) with value A (FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT)
    Args:
        client_options: MQTT5 ClientOptions dataclass.
    Returns:
        str: The encoded feature list string
    """

    features = []

    # A: retry_jitter_mode
    if client_options.retry_jitter_mode is not None:
        val = _retry_jitter_metrics_value(client_options.retry_jitter_mode)
        if val:
            features.append(f"{MetricsFeatureId.RETRY_JITTER_MODE}/{val}")

    # B: session_behavior
    if client_options.session_behavior is not None:
        val = _client_session_behavior_metrics_value(client_options.session_behavior)
        if val:
            features.append(f"{MetricsFeatureId.SESSION_BEHAVIOR}/{val}")

    # C: offline_queue_behavior
    if client_options.offline_queue_behavior is not None:
        val = _client_operation_queue_behavior_metrics_value(client_options.offline_queue_behavior)
        if val:
            features.append(f"{MetricsFeatureId.OFFLINE_QUEUE_BEHAVIOR}/{val}")

    # D: outbound_topic_alias_behavior
    if client_options.topic_aliasing_options is not None:
        if client_options.topic_aliasing_options.outbound_behavior is not None:
            val = _outbound_topic_alias_behavior_metrics_value(client_options.topic_aliasing_options.outbound_behavior)
            if val:
                features.append(f"{MetricsFeatureId.OUTBOUND_TOPIC_ALIAS_BEHAVIOR}/{val}")

    # E: inbound_topic_alias_behavior
    if client_options.topic_aliasing_options is not None:
        if client_options.topic_aliasing_options.inbound_behavior is not None:
            val = _inbound_topic_alias_behavior_metrics_value(client_options.topic_aliasing_options.inbound_behavior)
            if val:
                features.append(f"{MetricsFeatureId.INBOUND_TOPIC_ALIAS_BEHAVIOR}/{val}")

    # F: protocol_version - MQTT5 always uses client options
    features.append(f"{MetricsFeatureId.PROTOCOL_VERSION}/{MetricsProtocolVersionValue.MQTT5}")

    # G: socket_implementation - Detect based on platform
    features.append(f"{MetricsFeatureId.SOCKET_IMPLEMENTATION}/{_detect_socket_implementation()}")

    # H: http_proxy_type - Determine based on whether proxy uses TLS
    if client_options.http_proxy_options is not None:
        proxy_type = MetricsHttpProxyTypeValue.HTTPS  if getattr(client_options.http_proxy_options, 'tls_connection_options', None) is not None else MetricsHttpProxyTypeValue.HTTP
        features.append(f"{MetricsFeatureId.HTTP_PROXY_TYPE}/{proxy_type}")

    # I: certificate_source - Would need to be tracked from TLS context setup. This is set at a IoT SDK level

    # LOOK into it
    # J: tls_cipher_preference

    # K: minimum_tls_version - The minimum TLS version is set on TLSContextOptions but not stored/accessible from TLSContext.

    return ",".join(features)

# MQTT3 encoding list
def get_encoded_feature_list_mqtt3(proxy_options):
    """
    Generates encoded feature list for MQTT3 connections
    Args:
        proxy_options: Optional proxy options from Connection
    Returns:
        str: The encoded feature list string
    """
    features = [
        f"{MetricsFeatureId.PROTOCOL_VERSION}/{MetricsProtocolVersionValue.MQTT311}",
        f"{MetricsFeatureId.SOCKET_IMPLEMENTATION}/{_detect_socket_implementation()}"
    ]
    if proxy_options is not None:
        proxy_type = MetricsHttpProxyTypeValue.HTTPS if getattr(proxy_options, 'tls_connection_options', None) is not None else MetricsHttpProxyTypeValue.HTTP
        features.append(f"{MetricsFeatureId.HTTP_PROXY_TYPE}/{proxy_type}")

    return ",".join(features)


def merge_feature_lists(crt_features, user_features):
    """Merges CRT features with user-provided (SDK) features.
      User features take precedence for the same feature ID.

      Args:
          crt_features (str): CRT-generated feature list (e.g., "A/B,F/5,G/A")
          user_features (str): User-provided feature list from IoT SDK
      Returns:
          str: The merged feature list string
    """
    merged = {}
    # Parse CRT Features
    for pair in crt_features.split(","):
        if "/" in pair:
            fid, val = pair.split("/",1)
            merged[fid] = val

    #
    for pair in user_features.split(","):
        if "/" in pair:
            fid, val = pair.split("/", 1)
            merged[fid] = val
    return ",".join(f"{k}/{v}" for k ,v in sorted(merged.items()))

# Metrics creation
def create_metrics(user_metrics, crt_feature_list):
    """
    Creates the final IoTDeviceSDKMetrics
    The function sets the metrics according to following rules:
    1. libraryName: - set to default SDK Name. If the libraryName field is not set.
    2. metadata - CRTVersion : automatically set CRT version, not modifiable by user
    3. metadata - IOTSDKMetricsVersion: validates whether the metrics version matches the library's metrics version and process IoTSDKFeature
    4. metadata - IoTSDKFeature: merge the CRT feature and the input feature if the metrics version matches

    Args:
        user_metrics: Optional AWSIoTMetrics from IoT SDK
        crt_feature_list (str): Encoded CRT feature list
    Returns:
        AWSIoTMetrics: The final metrics object
    """

    from awscrt import __version__ as crt_version

    final_metrics = AWSIoTMetrics(
          library_name=user_metrics.library_name if user_metrics else "IoTDeviceSDK/Python"
    )

    # CRTVERSION: not modifiable by user, automatically set
    metadata = {"CRTVersion": crt_version}


    #Extract user_metadata from IoT SDK
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
    if (user_metrics_version is not None and user_metrics_version.isdigit() and int(user_metrics_version) == IOT_SDK_METRICS_FEATURE_VERSION and user_feature):
        metadata["IoTSDKFeature"] = merge_feature_lists(crt_feature_list,user_feature)
    else:
        metadata["IoTSDKFeature"] = merge_feature_lists(crt_feature_list,"")

    # Always set current metrics version
    metadata["IoTSDKMetricsVersion"] = str(IOT_SDK_METRICS_FEATURE_VERSION)

    final_metrics.metadata_entries = [IoTMetricsMetadata(key=k, value = v) for k,v in metadata.items()]
    return final_metrics


def create_metrics_mqtt5(client_options):
    """
    Creates final metrics for MQTT5 client.
    Args:
        client_options: MQTT5 ClientOptions dataclass
    Returns:
        AWSIoTMetrics: The final metrics object
    """
    crt_feature_list = get_encoded_feature_list(client_options)
    return create_metrics(client_options.metrics, crt_feature_list)

def create_metrics_mqtt3(user_metrics = None, proxy_options = None):
    """
    Creates final metrics for MQTT3 connection.
    Args:
        user_metrics: Optional AWSIoTMetrics from IoT SDK
        proxy_options: Optional proxy options from Connection
    Returns:
        AWSIoTMetrics: The final metrics object
    """
    crt_feature_list = get_encoded_feature_list_mqtt3(proxy_options)
    return create_metrics(user_metrics, crt_feature_list)
