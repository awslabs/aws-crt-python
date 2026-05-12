# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class IoTMetricsMetadataEntry:
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
        metadata_entries (Optional[list(IoTMetricsMetadataEntry)]): Optional list for storing key-value pairs of metadata

    """
    library_name: str = "IoTDeviceSDK/Python"
    metadata_entries: Optional[list[IoTMetricsMetadataEntry]] = None
