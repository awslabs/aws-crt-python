# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import sys
import unittest
from test import NativeResourceTest
from awscrt.aws_iot_metrics import (
    AWSIoTMetrics,
    IoTMetricsMetadata,
    MetricsFeatureId,
    MetricsProtocolVersionValue,
    MetricsSocketImplementationValue,
    MetricsHttpProxyTypeValue,
    IOT_SDK_METRICS_FEATURE_VERSION,
    _get_encoded_feature_list,
    _get_encoded_feature_list_mqtt3,
    _merge_feature_lists,
    create_metrics,
)
from awscrt.mqtt5 import (
    ClientOptions,
    ExponentialBackoffJitterMode,
    ClientSessionBehaviorType,
    ClientOperationQueueBehaviorType,
    OutboundTopicAliasBehaviorType,
    InboundTopicAliasBehaviorType,
    TopicAliasingOptions,
)
from awscrt.io import ClientTlsContext, TlsContextOptions, TlsConnectionOptions, TlsVersion, TlsCipherPref
from awscrt.http import HttpProxyOptions


def _expected_socket_value():
    if sys.platform == "win32":
        return MetricsSocketImplementationValue.WINSOCK
    return MetricsSocketImplementationValue.POSIX


class TestMinimalOptionsEncoding(NativeResourceTest):
    """Test encoding with minimal/default options."""

    def test_mqtt5_minimal(self):
        """MQTT5 with all defaults should only have protocol version and socket."""
        options = ClientOptions(host_name="localhost", port=8883)

        result = _get_encoded_feature_list(options)

        self.assertIn(f"{MetricsFeatureId.PROTOCOL_VERSION.value}/{MetricsProtocolVersionValue.MQTT5.value}", result)
        self.assertIn(f"{MetricsFeatureId.SOCKET_IMPLEMENTATION.value}/{_expected_socket_value().value}", result)
        parts = result.split(",")
        self.assertEqual(2, len(parts))

    def test_mqtt3_minimal(self):
        """MQTT3 with no proxy and no TLS should only have protocol version and socket."""
        result = _get_encoded_feature_list_mqtt3(proxy_options=None, tls_ctx=None)

        self.assertIn(f"{MetricsFeatureId.PROTOCOL_VERSION.value}/{MetricsProtocolVersionValue.MQTT311.value}", result)
        self.assertIn(f"{MetricsFeatureId.SOCKET_IMPLEMENTATION.value}/{_expected_socket_value().value}", result)
        parts = result.split(",")
        self.assertEqual(2, len(parts))

    def test_default_enum_values_omitted(self):
        """DEFAULT enum values should not appear in the encoded list."""
        options = ClientOptions(
            host_name="localhost",
            port=8883,
            retry_jitter_mode=ExponentialBackoffJitterMode.DEFAULT,
            session_behavior=ClientSessionBehaviorType.DEFAULT,
            offline_queue_behavior=ClientOperationQueueBehaviorType.DEFAULT,
        )

        result = _get_encoded_feature_list(options)

        self.assertNotIn(f"{MetricsFeatureId.RETRY_JITTER_MODE.value}/", result)
        self.assertNotIn(f"{MetricsFeatureId.SESSION_BEHAVIOR.value}/", result)
        self.assertNotIn(f"{MetricsFeatureId.OFFLINE_QUEUE_BEHAVIOR.value}/", result)


class TestOptionsWithMultipleNonDefaultFeaturesEncoding(NativeResourceTest):
    """Test encoding with multiple explicitly-set features."""

    def test_all_mqtt5_features_set(self):
        """MQTT5 with all features explicitly set to non-default values."""
        proxy = HttpProxyOptions(host_name="proxy.example.com", port=8080)

        tls_options = TlsContextOptions()
        tls_options.min_tls_ver = TlsVersion.TLSv1_2
        cipher_pref = TlsCipherPref.PQ_DEFAULT
        if cipher_pref.is_supported():
            tls_options.cipher_pref = cipher_pref
        tls_ctx = ClientTlsContext(tls_options)

        options = ClientOptions(
            host_name="localhost",
            port=8883,
            retry_jitter_mode=ExponentialBackoffJitterMode.FULL,
            session_behavior=ClientSessionBehaviorType.CLEAN,
            offline_queue_behavior=ClientOperationQueueBehaviorType.FAIL_ALL_ON_DISCONNECT,
            topic_aliasing_options=TopicAliasingOptions(
                outbound_behavior=OutboundTopicAliasBehaviorType.LRU,
                inbound_behavior=InboundTopicAliasBehaviorType.ENABLED,
            ),
            http_proxy_options=proxy,
            tls_ctx=tls_ctx,
        )

        result = _get_encoded_feature_list(options)

        self.assertIn("A/B", result)  # FULL
        self.assertIn("B/A", result)  # CLEAN
        self.assertIn("C/C", result)  # FAIL_ALL
        self.assertIn("D/B", result)  # LRU
        self.assertIn("E/A", result)  # ENABLED
        self.assertIn("F/5", result)  # MQTT5
        self.assertIn("H/A", result)  # HTTP proxy (no TLS on proxy)
        self.assertIn("K/D", result)  # TLSv1_2
        if cipher_pref.is_supported():
            self.assertIn("J/B", result)  # PQ_DEFAULT

    def test_alternate_values(self):
        """MQTT5 with alternate non-default values."""
        tls_options = TlsContextOptions()
        tls_options.min_tls_ver = TlsVersion.TLSv1_3
        cipher_pref = TlsCipherPref.PQ_TLSv1_0_2021_05
        if cipher_pref.is_supported():
            tls_options.cipher_pref = cipher_pref
        tls_ctx = ClientTlsContext(tls_options)

        proxy_tls_ctx = ClientTlsContext(TlsContextOptions())
        proxy_tls_conn_options = TlsConnectionOptions(proxy_tls_ctx)
        proxy = HttpProxyOptions(
            host_name="proxy.example.com", port=443,
            tls_connection_options=proxy_tls_conn_options)

        options = ClientOptions(
            host_name="localhost",
            port=8883,
            retry_jitter_mode=ExponentialBackoffJitterMode.DECORRELATED,
            session_behavior=ClientSessionBehaviorType.REJOIN_ALWAYS,
            offline_queue_behavior=ClientOperationQueueBehaviorType.FAIL_NON_QOS1_PUBLISH_ON_DISCONNECT,
            topic_aliasing_options=TopicAliasingOptions(
                outbound_behavior=OutboundTopicAliasBehaviorType.MANUAL,
                inbound_behavior=InboundTopicAliasBehaviorType.DISABLED,
            ),
            http_proxy_options=proxy,
            tls_ctx=tls_ctx,
        )

        result = _get_encoded_feature_list(options)

        self.assertIn("A/C", result)  # DECORRELATED
        self.assertIn("B/C", result)  # REJOIN_ALWAYS
        self.assertIn("C/A", result)  # FAIL_NON_QOS1
        self.assertIn("D/A", result)  # MANUAL
        self.assertIn("E/B", result)  # DISABLED
        self.assertIn("F/5", result)  # MQTT5
        self.assertIn("H/B", result)  # HTTPS proxy
        self.assertIn("K/E", result)  # TLSv1_3
        if cipher_pref.is_supported():
            self.assertIn("J/A", result)  # PQ_TLSv1_0_2021_05

    def test_mqtt3_with_proxy_and_tls(self):
        """MQTT3 with HTTPS proxy and TLS context."""
        tls_options = TlsContextOptions()
        tls_options.min_tls_ver = TlsVersion.TLSv1_2
        cipher_pref = TlsCipherPref.TLSv1_2_2025_07
        if cipher_pref.is_supported():
            tls_options.cipher_pref = cipher_pref
        tls_ctx = ClientTlsContext(tls_options)

        proxy_tls_ctx = ClientTlsContext(TlsContextOptions())
        proxy_tls_conn_options = TlsConnectionOptions(proxy_tls_ctx)
        proxy = HttpProxyOptions(
            host_name="proxy.example.com", port=443,
            tls_connection_options=proxy_tls_conn_options)

        result = _get_encoded_feature_list_mqtt3(proxy_options=proxy, tls_ctx=tls_ctx)

        self.assertIn("F/3", result)
        self.assertIn("H/B", result)  # HTTPS
        self.assertIn("K/D", result)  # TLSv1_2
        if cipher_pref.is_supported():
            self.assertIn("J/C", result)  # TLSv1_2_2025_07


class TestMergeFeatureLists(NativeResourceTest):
    """Test feature list merging logic."""

    def test_user_overrides_crt(self):
        """User features take precedence over CRT features for same feature ID."""
        result = _merge_feature_lists("A/B,F/5", "A/C")
        # User's A/C overwrites CRT's A/B
        self.assertEqual("A/C,F/5", result)

    def test_user_overrides_multiple_crt_features(self):
        """User can override multiple CRT features at once."""
        result = _merge_feature_lists("A/B,F/5,G/A,K/D", "A/C,F/3,K/E")
        # User overrides A, F, K; G remains from CRT
        self.assertEqual("A/C,F/3,G/A,K/E", result)

    def test_empty_user_features(self):
        result = _merge_feature_lists("F/5,G/A", "")
        self.assertEqual("F/5,G/A", result)

    def test_empty_crt_features(self):
        result = _merge_feature_lists("", "A/B")
        self.assertEqual("A/B", result)

    def test_sorted_output(self):
        result = _merge_feature_lists("G/A,F/5", "A/B")
        self.assertEqual("A/B,F/5,G/A", result)

    def test_disjoint_features(self):
        result = _merge_feature_lists("F/5,G/A", "I/A,K/D")
        self.assertEqual("F/5,G/A,I/A,K/D", result)

    def test_both_empty(self):
        result = _merge_feature_lists("", "")
        self.assertEqual("", result)


class TestCreateMetricsWithDefaultOptions(NativeResourceTest):
    """Test create_metrics with no user metrics or default user metrics."""

    def test_none_user_metrics(self):
        result = create_metrics(None, "F/5,G/A")

        self.assertEqual("IoTDeviceSDK/Python", result.library_name)
        metadata_dict = {e.key: e.value for e in result.metadata_entries}
        self.assertIn("CRTVersion", metadata_dict)
        self.assertEqual("F/5,G/A", metadata_dict["IoTSDKFeature"])
        self.assertEqual(str(IOT_SDK_METRICS_FEATURE_VERSION), metadata_dict["IoTSDKMetricsVersion"])

    def test_empty_user_metrics(self):
        user = AWSIoTMetrics()
        result = create_metrics(user, "F/5,G/A")

        self.assertEqual("IoTDeviceSDK/Python", result.library_name)
        metadata_dict = {e.key: e.value for e in result.metadata_entries}
        self.assertEqual("F/5,G/A", metadata_dict["IoTSDKFeature"])

    def test_version_always_set(self):
        result = create_metrics(None, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}
        self.assertEqual(str(IOT_SDK_METRICS_FEATURE_VERSION), metadata_dict["IoTSDKMetricsVersion"])


class TestCreateMetricsWithUserFeaturesMerged(NativeResourceTest):
    """Test that user features are merged when version matches."""

    def test_user_feature_added(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKMetricsVersion", value="1"),
            IoTMetricsMetadata(key="IoTSDKFeature", value="I/A"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertIn("I/A", metadata_dict["IoTSDKFeature"])
        self.assertIn("F/5", metadata_dict["IoTSDKFeature"])
        self.assertIn("G/A", metadata_dict["IoTSDKFeature"])

    def test_user_feature_overrides_crt(self):
        """User feature takes precedence over CRT feature for same ID."""
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKMetricsVersion", value="1"),
            IoTMetricsMetadata(key="IoTSDKFeature", value="F/3,I/B"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertIn("F/3", metadata_dict["IoTSDKFeature"])
        self.assertNotIn("F/5", metadata_dict["IoTSDKFeature"])
        self.assertIn("I/B", metadata_dict["IoTSDKFeature"])

    def test_empty_user_feature_string(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKMetricsVersion", value="1"),
            IoTMetricsMetadata(key="IoTSDKFeature", value=""),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertEqual("F/5,G/A", metadata_dict["IoTSDKFeature"])


class TestCreateMetricsWithVersionMismatch(NativeResourceTest):
    """Test that user features are ignored when version doesn't match."""

    def test_higher_version(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKMetricsVersion", value="99"),
            IoTMetricsMetadata(key="IoTSDKFeature", value="I/A"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertNotIn("I/A", metadata_dict["IoTSDKFeature"])
        self.assertIn("F/5", metadata_dict["IoTSDKFeature"])

    def test_lower_version(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKMetricsVersion", value="0"),
            IoTMetricsMetadata(key="IoTSDKFeature", value="I/A"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertNotIn("I/A", metadata_dict["IoTSDKFeature"])

    def test_non_numeric_version(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKMetricsVersion", value="abc"),
            IoTMetricsMetadata(key="IoTSDKFeature", value="I/A"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertNotIn("I/A", metadata_dict["IoTSDKFeature"])

    def test_no_version_set(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKFeature", value="I/A"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertNotIn("I/A", metadata_dict["IoTSDKFeature"])


class TestCreateMetricsCRTVersionNotModifiable(NativeResourceTest):
    """Test that CRTVersion cannot be overridden by user."""

    def test_user_cannot_override_crt_version(self):
        from awscrt import __version__ as actual_version

        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="CRTVersion", value="fake_version"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertEqual(actual_version, metadata_dict["CRTVersion"])
        self.assertNotEqual("fake_version", metadata_dict["CRTVersion"])

    def test_empty_crt_version_overridden(self):
        from awscrt import __version__ as actual_version

        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="CRTVersion", value=""),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertEqual(actual_version, metadata_dict["CRTVersion"])


class TestCreateMetricsPreservesOtherUserMetadata(NativeResourceTest):
    """Test that non-reserved user metadata keys are preserved."""

    def test_sdk_version_preserved(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="IoTSDKVersion", value="2.0.0"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertEqual("2.0.0", metadata_dict["IoTSDKVersion"])

    def test_custom_key_preserved(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="CustomKey", value="custom_value"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertEqual("custom_value", metadata_dict["CustomKey"])

    def test_mixed_metadata(self):
        user = AWSIoTMetrics()
        user.metadata_entries = [
            IoTMetricsMetadata(key="CRTVersion", value="should_be_ignored"),
            IoTMetricsMetadata(key="IoTSDKVersion", value="2.0.0"),
            IoTMetricsMetadata(key="CustomKey", value="val"),
        ]

        result = create_metrics(user, "F/5,G/A")
        metadata_dict = {e.key: e.value for e in result.metadata_entries}

        self.assertNotEqual("should_be_ignored", metadata_dict["CRTVersion"])
        self.assertEqual("2.0.0", metadata_dict["IoTSDKVersion"])
        self.assertEqual("val", metadata_dict["CustomKey"])

    def test_custom_library_name(self):
        user = AWSIoTMetrics(library_name="MyCustomSDK/1.0")

        result = create_metrics(user, "F/5,G/A")

        self.assertEqual("MyCustomSDK/1.0", result.library_name)


if __name__ == '__main__':
    unittest.main()
