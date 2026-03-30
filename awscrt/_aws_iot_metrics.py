# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from dataclasses import dataclass

@dataclass
class AWSIoTMetrics:
    """
    Configuration for IoT SDK metrics that are embedded in MQTT Connect Packet username field.

    Args:
        library_name (str): The SDK library name (e.g., "IoTDeviceSDK/Python")

    """
    library_name: str = "IoTDeviceSDK/Python"
