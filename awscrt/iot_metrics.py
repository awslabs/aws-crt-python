# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

"""
IoT SDK Metrics

This module provides data structures and utilities for IoT SDK metrics collection
that are embedded in MQTT CONNECT packet username fields.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from awscrt import __version__


@dataclass
class SdkMetrics:
    """
    Configuration for IoT SDK metrics that are embedded in MQTT username field.

    Args:
        library_name (str): The SDK library name (e.g., "IoTDeviceSDK/Python")

    """
    library_name: str = "IoTDeviceSDK/Python"
