"""
MQTT Request Response module
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from dataclasses import dataclass
from typing import Callable, Union
from awscrt import NativeResource, mqtt5, mqtt
import _awscrt


@dataclass
class RequestResponseClientOptions:
    """
    MQTT-based request-response client configuration options

    Args:
        max_request_response_subscriptions (int):  Maximum number of subscriptions that the client will concurrently use for request-response operations
        max_streaming_subscriptions (int):  Maximum number of subscriptions that the client will concurrently use for streaming operations
        operation_timeout_in_seconds (Optional[int]):  Duration, in seconds, that a request-response operation will wait for completion before giving up
    """
    max_request_response_subscriptions: int
    max_streaming_subscriptions: int
    operation_timeout_in_seconds: 'Optional[int]' = 60

    def validate(self):
        assert isinstance(self.max_request_response_subscriptions, int)
        assert isinstance(self.max_streaming_subscriptions, int)
        assert isinstance(self.operation_timeout_in_seconds, int)


class Client(NativeResource):
    """
    MQTT-based request-response client tuned for AWS MQTT services.

    Supports streaming operations (listen to a stream of modeled events from an MQTT topic) and request-response
    operations (performs the subscribes, publish, and incoming publish correlation and error checking needed to
    perform simple request-response operations over MQTT).

    Args:
        protocol_client (Union[mqtt5.Client, mqtt.Connection]): MQTT client to use as transport
        client_options (ClientOptions): The ClientOptions dataclass to used to configure the new request response Client.

    """

    def __init__(self, protocol_client: Union[mqtt5.Client, mqtt.Connection],
                 client_options: RequestResponseClientOptions):

        assert isinstance(protocol_client, mqtt5.Client) or isinstance(protocol_client, mqtt.Connection)
        assert isinstance(client_options, RequestResponseClientOptions)
        client_options.validate()

        super().__init__()

        if isinstance(protocol_client, mqtt5.Client):
            self._binding = _awscrt.mqtt_request_response_client_new_from_5(protocol_client, client_options)
        else:
            self._binding = _awscrt.mqtt_request_response_client_new_from_311(protocol_client, client_options)
