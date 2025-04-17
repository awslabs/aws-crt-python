"""
MQTT Request Response module
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from dataclasses import dataclass
from typing import Union
from awscrt import NativeResource, mqtt5, mqtt, exceptions
from concurrent.futures import Future
import _awscrt
import collections.abc


@dataclass
class Response:
    """
    Encapsulates a response to an AWS IoT Core MQTT-based service request

    Args:
        topic (str):  MQTT Topic that the response was received on.
        payload (Optional[bytes]):  The payload of the response.
    """
    topic: str
    payload: 'Optional[bytes]' = None


@dataclass
class ResponsePath:
    """
    A response path is a pair of values - MQTT topic and a JSON path - that describe how a response to
    an MQTT-based request may arrive.  For a given request type, there may be multiple response paths and each
    one is associated with a separate JSON schema for the response body.

    Args:
        topic (str):  MQTT topic that a response may arrive on.
        correlation_token_json_path (Optional[str]):  JSON path for finding correlation tokens within payloads that arrive on this path's topic.
    """
    topic: str
    correlation_token_json_path: 'Optional[str]' = None

    def validate(self):
        assert isinstance(self.topic, str)
        assert isinstance(self.correlation_token_json_path, str) or self.correlation_token_json_path is None


@dataclass
class RequestResponseOperationOptions:
    """
    Configuration options for an MQTT-based request-response operation.

    Args:
        subscription_topic_filters (Sequence[str]):  Set of topic filters that should be subscribed to in order to cover all possible response paths.  Sometimes using wildcards can cut down on the subscriptions needed; other times that isn't valid.
        response_paths (Sequence[ResponsePath]):  Set of all possible response paths associated with this request type.
        publish_topic (str): Topic to publish the request to once response subscriptions have been established.
        payload (bytes): Payload to publish to 'publishTopic' in order to initiate the request
        correlation_token (Optional[str]): Correlation token embedded in the request that must be found in a response message.  This can be null to support certain services which don't use correlation tokens.  In that case, the client only allows one token-less request at a time.
    """
    subscription_topic_filters: 'Sequence[str]'
    response_paths: 'Sequence[ResponsePath]'
    publish_topic: str
    payload: bytes
    correlation_token: 'Optional[str]' = None

    def validate(self):
        assert isinstance(self.subscription_topic_filters, collections.abc.Sequence)
        for topic_filter in self.subscription_topic_filters:
            assert isinstance(topic_filter, str)

        assert isinstance(self.response_paths, collections.abc.Sequence)
        for response_path in self.response_paths:
            response_path.validate()

        assert isinstance(self.publish_topic, str)
        assert isinstance(self.payload, bytes)
        assert isinstance(self.correlation_token, str) or self.correlation_token is None


@dataclass
class StreamingOperationOptions:
    """
    Configuration options for an MQTT-based streaming operation.

    Args:
        subscription_topic_filter (str):  Topic filter that the streaming operation should listen on
    """
    subscription_topic_filter: str


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

    def make_request(self, options: RequestResponseOperationOptions):
        options.validate()

        future = Future()

        def on_request_complete(error_code, topic, payload):
            if error_code != 0:
                future.set_exception(exceptions.from_code(error_code))
            else:
                response = Response(topic=topic, payload=payload)
                future.set_result(response)

        _awscrt.mqtt_request_response_client_make_request(self._binding,
                                                          options.subscription_topic_filters,
                                                          options.response_paths,
                                                          options.publish_topic,
                                                          options.payload,
                                                          options.correlation_token,
                                                          on_request_complete)

        return future
