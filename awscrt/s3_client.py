"""
S3 client
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from concurrent.futures import Future
from enum import IntEnum
from awscrt import NativeResource
import awscrt.exceptions
from awscrt.http import HttpProxyOptions, HttpRequest
from awscrt.io import ClientBootstrap, ClientTlsContext, SocketOptions

class Client(NativeResource):
    """S3 client

    Args:

    """

    __slots__=()

    def __init__(self):
        self._binding = _awscrt.s3_client_new()