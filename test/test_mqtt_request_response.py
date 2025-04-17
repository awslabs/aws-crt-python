# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
from awscrt.mqtt_request_response import StreamingOperationOptions
from test import NativeResourceTest
from awscrt import io, mqtt5, mqtt_request_response, mqtt

from concurrent.futures import Future
import os
import time
import unittest
import uuid

TIMEOUT = 30.0


def create_client_id():
    return f"aws-crt-python-unit-test-{uuid.uuid4()}"


def _get_env_variable(env_name):
    env_data = os.environ.get(env_name)
    if not env_data:
        raise unittest.SkipTest(f"test requires env var: {env_name}")
    return env_data


class MqttRequestResponse5TestCallbacks():
    def __init__(self):
        self.future_connection_success = Future()
        self.future_stopped = Future()

    def ws_handshake_transform(self, transform_args):
        transform_args.set_done()

    def on_publish_received(self, publish_received_data: mqtt5.PublishReceivedData):
        pass

    def on_lifecycle_stopped(self, lifecycle_stopped: mqtt5.LifecycleStoppedData):
        if self.future_stopped:
            self.future_stopped.set_result(None)

    def on_lifecycle_attempting_connect(self, lifecycle_attempting_connect: mqtt5.LifecycleAttemptingConnectData):
        pass

    def on_lifecycle_connection_success(self, lifecycle_connection_success: mqtt5.LifecycleConnectSuccessData):
        if self.future_connection_success:
            self.future_connection_success.set_result(lifecycle_connection_success)

    def on_lifecycle_connection_failure(self, lifecycle_connection_failure: mqtt5.LifecycleConnectFailureData):
        if self.future_connection_success:
            if self.future_connection_success.done():
                pass
            else:
                self.future_connection_success.set_exception(lifecycle_connection_failure.exception)

    def on_lifecycle_disconnection(self, lifecycle_disconnect_data: mqtt5.LifecycleDisconnectData):
        pass


def _empty_response_paths(options):
    options.response_paths = []


def _invalidate_response_path_topic(options):
    options.response_paths[0].topic = "a/#/b"


def _none_response_path_topic(options):
    options.response_paths[0].topic = None


def _missing_response_path_topic(options):
    del options.response_paths[0].topic


def _type_mismatch_response_path_topic(options):
    options.response_paths[0].topic = 57.3


def _type_mismatch_response_path_correlation_token_json_path(options):
    options.response_paths[0].correlation_token_json_path = []


def _type_mismatch_response_paths(options):
    options.response_paths = "hello"


def _invalidate_subscription_topic_filter(options):
    options.subscription_topic_filters[0] = "a/#/c"


def _type_mismatch_subscription_topic_filter(options):
    options.subscription_topic_filters[0] = ["thirty", 30]


def _type_mismatch_subscriptions(options):
    options.subscription_topic_filters = 50


def _empty_subscription_topic_filters(options):
    options.subscription_topic_filters = []


def _none_publish_topic(options):
    options.publish_topic = None


def _bad_publish_topic(options):
    options.publish_topic = "#/b/c"


def _type_mismatch_publish_topic(options):
    options.publish_topic = [["oof"]]


def _type_mismatch_correlation_token(options):
    options.correlation_token = [-1]

def _subscription_topic_filter_none(options):
    options.subscription_topic_filter = None


def _type_mismatch_stream_subscription_topic_filter(options):
    options.subscription_topic_filter = 6


def _type_mismatch_subscription_status_listener(options):
    options.subscription_status_listener = "string"


def _type_mismatch_incoming_publish_listener(options):
    options.incoming_publish_listener = "string"


class MqttRequestResponseClientTest(NativeResourceTest):

    def _create_client5(self):

        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        client_options = mqtt5.ClientOptions(
            host_name=input_host_name,
            port=8883
        )

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        client_options.tls_ctx = io.ClientTlsContext(tls_ctx_options)

        client_options.connect_options = mqtt5.ConnectPacket()
        client_options.connect_options.client_id = create_client_id()

        callbacks = MqttRequestResponse5TestCallbacks()
        client_options.on_lifecycle_event_stopped_fn = callbacks.on_lifecycle_stopped
        client_options.on_lifecycle_event_connection_success_fn = callbacks.on_lifecycle_connection_success
        client_options.on_lifecycle_event_connection_failure_fn = callbacks.on_lifecycle_connection_failure
        client_options.on_lifecycle_event_stopped_fn = callbacks.on_lifecycle_stopped

        protocol_client = mqtt5.Client(client_options)
        protocol_client.start()

        callbacks.future_connection_success.result(TIMEOUT)

        return protocol_client, callbacks

    def _shutdown5(self, protocol_client, callbacks):

        protocol_client.stop()
        callbacks.future_stopped.result(TIMEOUT)

    def _create_client311(self):

        input_host_name = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_HOST")
        input_cert = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_CERT")
        input_key = _get_env_variable("AWS_TEST_MQTT5_IOT_CORE_RSA_KEY")

        tls_ctx_options = io.TlsContextOptions.create_client_with_mtls_from_path(
            input_cert,
            input_key
        )
        tls_ctx = io.ClientTlsContext(tls_ctx_options)

        client = mqtt.Client(None, tls_ctx)

        protocol_client = mqtt.Connection(
            client=client,
            client_id=create_client_id(),
            host_name=input_host_name,
            port=8883,
            ping_timeout_ms=10000,
            keep_alive_secs=30
        )
        protocol_client.connect().result(TIMEOUT)

        return protocol_client

    def _shutdown311(self, protocol_client):
        protocol_client.disconnect().result(TIMEOUT)

    def _create_rr_client(
            self,
            protocol_client,
            max_request_response_subscriptions,
            max_streaming_subscriptions,
            operation_timeout_seconds):
        rr_client_options = mqtt_request_response.ClientOptions(
            max_request_response_subscriptions, max_streaming_subscriptions)
        rr_client_options.operation_timeout_in_seconds = operation_timeout_seconds

        rr_client = mqtt_request_response.Client(protocol_client, rr_client_options)

        return rr_client

    def _do_mqtt5_test(self, test_callable):
        (protocol_client, callbacks) = self._create_client5()

        test_callable(protocol_client)

        self._shutdown5(protocol_client, callbacks)

    def _do_mqtt311_test(self, test_callable):
        protocol_client = self._create_client311()

        test_callable(protocol_client)

        self._shutdown311(protocol_client)

    def _create_get_shadow_request(self, thing_name, use_correlation_token):
        topic_prefix = f"$aws/things/{thing_name}/shadow/get"

        request_options = mqtt_request_response.RequestOptions(
            subscription_topic_filters=[f"{topic_prefix}/+"],
            response_paths=[
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/accepted"),
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/rejected")
            ],
            publish_topic=topic_prefix,
            payload="{}".encode()
        )

        if use_correlation_token:
            correlation_token = f"{uuid.uuid4()}"
            request_options.response_paths[0].correlation_token_json_path = "clientToken"
            request_options.response_paths[1].correlation_token_json_path = "clientToken"
            request_options.payload = f'{{"clientToken":"{correlation_token}"}}'.encode()
            request_options.correlation_token = correlation_token

        return request_options

    def _do_get_shadow_success_no_such_shadow(self, rr_client, thing_name, use_correlation_token):
        request_options = self._create_get_shadow_request(thing_name, use_correlation_token)

        request_future = rr_client.make_request(request_options)
        response = request_future.result()

        self.assertEqual(request_options.response_paths[1].topic, response.topic,
                         "Expected response to come in on rejected topic")
        payload = str(response.payload)

        self.assertIn("No shadow exists with name", payload)

    def _do_get_shadow_success_no_such_shadow_test(self, protocol_client, use_correlation_token):
        rr_client = self._create_rr_client(protocol_client, 2, 2, 30)

        thing_name = f"tn-{uuid.uuid4()}"
        self._do_get_shadow_success_no_such_shadow(rr_client, thing_name, use_correlation_token)

    def _do_get_shadow_success(self, rr_client, thing_name, use_correlation_token):
        request_options = self._create_get_shadow_request(thing_name, use_correlation_token)

        request_future = rr_client.make_request(request_options)
        response = request_future.result()

        self.assertEqual(request_options.response_paths[0].topic, response.topic,
                         "Expected response to come in on accepted topic")

        payload = str(response.payload)
        self.assertIn("magic", payload)

    def _do_update_shadow_success(self, rr_client, thing_name, use_correlation_token):
        topic_prefix = f"$aws/things/{thing_name}/shadow/update"

        request_options = mqtt_request_response.RequestOptions(
            subscription_topic_filters=[f"{topic_prefix}/accepted", f"{topic_prefix}/rejected"],
            response_paths=[
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/accepted"),
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/rejected")
            ],
            publish_topic=topic_prefix,
            payload="".encode()
        )

        desired_state = f'{{"magic":"value"}}'

        if use_correlation_token:
            correlation_token = f"{uuid.uuid4()}"
            payload = f'{{"clientToken": "{correlation_token}","state": {{"desired": {desired_state}}}}}'
            request_options.response_paths[0].correlation_token_json_path = "clientToken"
            request_options.response_paths[1].correlation_token_json_path = "clientToken"
            request_options.payload = payload.encode()
            request_options.correlation_token = correlation_token
        else:
            request_options.payload = f'{{"state":{{"desired":{desired_state}}}}}'.encode()

        request_future = rr_client.make_request(request_options)
        response = request_future.result()

        self.assertEqual(request_options.response_paths[0].topic, response.topic,
                         "Expected response to come in on accepted topic")

        payload = str(response.payload)
        self.assertIn("magic", payload)

    def _do_delete_shadow_success(self, rr_client, thing_name, use_correlation_token):
        topic_prefix = f"$aws/things/{thing_name}/shadow/delete"

        request_options = mqtt_request_response.RequestOptions(
            subscription_topic_filters=[f"{topic_prefix}/+"],
            response_paths=[
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/accepted"),
                mqtt_request_response.ResponsePath(topic=f"{topic_prefix}/rejected")
            ],
            publish_topic=topic_prefix,
            payload="{}".encode()
        )

        if use_correlation_token:
            correlation_token = f"{uuid.uuid4()}"
            request_options.response_paths[0].correlation_token_json_path = "clientToken"
            request_options.response_paths[1].correlation_token_json_path = "clientToken"
            request_options.payload = f'{{"clientToken":"{correlation_token}"}}'.encode()
            request_options.correlation_token = correlation_token

        request_future = rr_client.make_request(request_options)
        response = request_future.result()

        self.assertEqual(request_options.response_paths[0].topic, response.topic,
                         "Expected response to come in on accepted topic")

        payload = str(response.payload)
        self.assertIn("version", payload)

    def _do_update_delete_shadow_success_test(self, protocol_client, use_correlation_token):
        rr_client = self._create_rr_client(protocol_client, 2, 2, 30)

        # get should return non-existence
        thing_name = f"tn-{uuid.uuid4()}"

        try:
            self._do_get_shadow_success_no_such_shadow(rr_client, thing_name, use_correlation_token)

            # update shadow to create
            self._do_update_shadow_success(rr_client, thing_name, use_correlation_token)

            # eventual consistency worries
            time.sleep(2)

            # get should now return the shadow state
            self._do_get_shadow_success(rr_client, thing_name, use_correlation_token)
        finally:
            # delete shadow
            self._do_delete_shadow_success(rr_client, thing_name, use_correlation_token)

    def _do_stream_success_test(self, protocol_client):
        rr_client = self._create_rr_client(protocol_client, 2, 2, 30)

        thing_name = f"tn-{uuid.uuid4()}"
        topic = f"not/a/valid/topic/{thing_name}"
        payload = b'hello'

        subscribed_future = Future()
        publish_received_future = Future()

        def on_subscription_status_changed(event):
            if event.type == mqtt_request_response.SubscriptionStatusEventType.SUBSCRIPTION_ESTABLISHED:
                subscribed_future.set_result(True)

        def on_incoming_publish(event):
            if event.topic == topic and event.payload == payload:
                publish_received_future.set_result(True)

        stream_options = StreamingOperationOptions(topic, on_subscription_status_changed, on_incoming_publish)
        stream = rr_client.create_stream(stream_options)

        stream.open()

        assert subscribed_future.result(30)

        if isinstance(protocol_client, mqtt5.Client):
            publish = mqtt5.PublishPacket(
                payload=payload,
                qos=mqtt5.QoS.AT_LEAST_ONCE,
                topic=topic
            )
            protocol_client.publish(publish)
        else:
            protocol_client.publish(topic, payload, mqtt.QoS.AT_LEAST_ONCE)

        assert publish_received_future.result(30)

    def _do_get_shadow_failure_test(self, protocol_client, options_transform):
        rr_client = self._create_rr_client(protocol_client, 2, 2, 30)

        thing_name = f"tn-{uuid.uuid4()}"
        request_options = self._create_get_shadow_request(thing_name, True)
        options_transform(request_options)

        self.assertRaises(Exception, lambda: rr_client.make_request(request_options))

    def _do_get_shadow_future_failure_test(self, protocol_client, options_transform):
        rr_client = self._create_rr_client(protocol_client, 2, 2, 30)

        thing_name = f"tn-{uuid.uuid4()}"
        request_options = self._create_get_shadow_request(thing_name, True)
        options_transform(request_options)

        response_future = rr_client.make_request(request_options)

        self.assertRaises(Exception, lambda: response_future.result())

    def _do_create_stream_failure_test(self, protocol_client, options_transform):
        rr_client = self._create_rr_client(protocol_client, 2, 2, 30)

        thing_name = f"tn-{uuid.uuid4()}"
        stream_options = mqtt_request_response.StreamingOperationOptions(f"not/a/real/thing/{thing_name}")
        options_transform(stream_options)

        self.assertRaises(Exception, lambda: rr_client.create_stream(stream_options))

    # ==============================================================
    #             CREATION SUCCESS TEST CASES
    # ==============================================================

    def test_client_creation_success5(self):
        self._do_mqtt5_test(lambda protocol_client: self._create_rr_client(protocol_client, 2, 2, 30))

    def test_client_creation_success311(self):
        self._do_mqtt311_test(lambda protocol_client: self._create_rr_client(protocol_client, 2, 2, 30))

    # ==============================================================
    #             CREATION FAILURE TEST CASES
    # ==============================================================

    def test_client_creation_failure_no_protocol_client(self):
        self.assertRaises(Exception, self._create_rr_client, None, 2, 2, 30)

    def test_client_creation_failure_zero_request_response_subscriptions5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 0, 2, 30))

    def test_client_creation_failure_zero_request_response_subscriptions311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 0, 2, 30))

    def test_client_creation_failure_negative_request_response_subscriptions5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, -2, 2, 30))

    def test_client_creation_failure_negative_request_response_subscriptions311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, -2, 2, 30))

    def test_client_creation_failure_no_request_response_subscriptions5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, None, 2, 30))

    def test_client_creation_failure_no_request_response_subscriptions311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, None, 2, 30))

    def test_client_creation_failure_request_response_subscriptions_type_mismatch5(self):
        self._do_mqtt5_test(
            lambda protocol_client: self.assertRaises(
                Exception,
                self._create_rr_client,
                protocol_client,
                "None",
                2,
                30))

    def test_client_creation_failure_request_response_subscriptions_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, "None", 2, 30))

    def test_client_creation_failure_negative_streaming_subscriptions5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, -2, 30))

    def test_client_creation_failure_negative_streaming_subscriptions311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, -2, 30))

    def test_client_creation_failure_no_streaming_subscriptions5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, None, 30))

    def test_client_creation_failure_no_streaming_subscriptions311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, None, 30))

    def test_client_creation_failure_streaming_subscriptions_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, [], 30))

    def test_client_creation_failure_streaming_subscriptions_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, {}, 30))

    def test_client_creation_failure_negative_operation_timeout5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, 2, -30))

    def test_client_creation_failure_negative_operation_timeout311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, 2, -30))

    def test_client_creation_failure_no_operation_timeout5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, 2, None))

    def test_client_creation_failure_no_operation_timeout311(self):
        self._do_mqtt311_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, 2, None))

    def test_client_creation_failure_operation_timeout_invalid5(self):
        self._do_mqtt5_test(lambda protocol_client: self.assertRaises(
            Exception, self._create_rr_client, protocol_client, 2, 2, ["uffdah"]))

    def test_client_creation_failure_operation_timeout_invalid311(self):
        self._do_mqtt311_test(
            lambda protocol_client: self.assertRaises(
                Exception,
                self._create_rr_client,
                protocol_client,
                2,
                2,
                777777777777777777777777777777777777))

    # ==============================================================
    #             make_request SUCCESS TEST CASES
    # ==============================================================

    def test_get_shadow_success_no_such_shadow5(self):
        self._do_mqtt5_test(
            lambda protocol_client: self._do_get_shadow_success_no_such_shadow_test(
                protocol_client, True))

    def test_get_shadow_success_no_such_shadow311(self):
        self._do_mqtt311_test(
            lambda protocol_client: self._do_get_shadow_success_no_such_shadow_test(
                protocol_client, True))

    def test_get_shadow_success_no_such_shadow_no_correlation_token5(self):
        self._do_mqtt5_test(
            lambda protocol_client: self._do_get_shadow_success_no_such_shadow_test(
                protocol_client, False))

    def test_get_shadow_success_no_such_shadow_no_correlation_token311(self):
        self._do_mqtt311_test(
            lambda protocol_client: self._do_get_shadow_success_no_such_shadow_test(
                protocol_client, False))

    def test_update_delete_shadow_success5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_update_delete_shadow_success_test(protocol_client, True))

    def test_update_delete_shadow_success311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_update_delete_shadow_success_test(protocol_client, True))

    def test_update_delete_shadow_success_no_correlation_token5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_update_delete_shadow_success_test(protocol_client, False))

    def test_update_delete_shadow_success_no_correlation_token311(self):
        self._do_mqtt311_test(
            lambda protocol_client: self._do_update_delete_shadow_success_test(
                protocol_client, False))

    # ==============================================================
    #             make_request FAILURE TEST CASES
    # ==============================================================

    def test_get_shadow_failure_no_response_paths5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _empty_response_paths(options)))

    def test_get_shadow_failure_no_response_paths311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _empty_response_paths(options)))

    def test_get_shadow_failure_invalid_response_path_topic5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_future_failure_test(
            protocol_client, lambda options: _invalidate_response_path_topic(options)))

    def test_get_shadow_failure_invalid_response_path_topic311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_future_failure_test(
            protocol_client, lambda options: _invalidate_response_path_topic(options)))

    def test_get_shadow_failure_none_response_path_topic5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _none_response_path_topic(options)))

    def test_get_shadow_failure_none_response_path_topic311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _none_response_path_topic(options)))

    def test_get_shadow_failure_missing_response_path_topic5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _missing_response_path_topic(options)))

    def test_get_shadow_failure_missing_response_path_topic311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _missing_response_path_topic(options)))

    def test_get_shadow_failure_response_path_topic_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_response_path_topic(options)))

    def test_get_shadow_failure_response_path_topic_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_response_path_topic(options)))

    def test_get_shadow_failure_response_path_correlation_token_json_path_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_response_path_correlation_token_json_path(options)))

    def test_get_shadow_failure_response_path_correlation_token_json_path_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_response_path_correlation_token_json_path(options)))

    def test_get_shadow_failure_response_paths_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_response_paths(options)))

    def test_get_shadow_failure_response_paths_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_response_paths(options)))

    def test_get_shadow_failure_invalid_subscription_topic5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_future_failure_test(
            protocol_client, lambda options: _invalidate_subscription_topic_filter(options)))

    def test_get_shadow_failure_invalid_subscription_topic311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_future_failure_test(
            protocol_client, lambda options: _invalidate_subscription_topic_filter(options)))

    def test_get_shadow_failure_subscription_topic_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_subscription_topic_filter(options)))

    def test_get_shadow_failure_subscription_topic_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_subscription_topic_filter(options)))

    def test_get_shadow_failure_subscriptions_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_subscriptions(options)))

    def test_get_shadow_failure_subscriptions_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_subscriptions(options)))

    def test_get_shadow_failure_empty_subscriptions5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _empty_subscription_topic_filters(options)))

    def test_get_shadow_failure_empty_subscriptions311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _empty_subscription_topic_filters(options)))

    def test_get_shadow_failure_none_publish_topic5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _none_publish_topic(options)))

    def test_get_shadow_failure_none_publish_topic311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _none_publish_topic(options)))

    def test_get_shadow_failure_bad_publish_topic5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_future_failure_test(
            protocol_client, lambda options: _bad_publish_topic(options)))

    def test_get_shadow_failure_bad_publish_topic311(self):
        self._do_mqtt311_test(
            lambda protocol_client: self._do_get_shadow_future_failure_test(
                protocol_client,
                lambda options: _bad_publish_topic(options)))

    def test_get_shadow_failure_publish_topic_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_publish_topic(options)))

    def test_get_shadow_failure_publish_topic_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_publish_topic(options)))

    def test_get_shadow_failure_correlation_token_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_correlation_token(options)))

    def test_get_shadow_failure_correlation_token_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_get_shadow_failure_test(
            protocol_client, lambda options: _type_mismatch_correlation_token(options)))

    # ==============================================================
    #             streaming operation SUCCESS TEST CASES
    # ==============================================================

    def test_streaming_operation_success5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_stream_success_test(protocol_client))

    def test_streaming_operation_success311(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_stream_success_test(protocol_client))

    # ==============================================================
    #             create_stream FAILURE TEST CASES
    # ==============================================================
    def test_create_stream_failure_subscription_topic_filter_none5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _subscription_topic_filter_none(options)))

    def test_create_stream_failure_subscription_topic_filter_none311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _subscription_topic_filter_none(options)))

    def test_create_stream_failure_subscription_topic_filter_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _type_mismatch_stream_subscription_topic_filter(options)))

    def test_create_stream_failure_subscription_topic_filter_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _type_mismatch_stream_subscription_topic_filter(options)))

    def test_create_stream_failure_subscription_status_listener_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _type_mismatch_subscription_status_listener(options)))

    def test_create_stream_failure_subscription_status_listener_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _type_mismatch_subscription_status_listener(options)))

    def test_create_stream_failure_incoming_publish_listener_type_mismatch5(self):
        self._do_mqtt5_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _type_mismatch_incoming_publish_listener(options)))

    def test_create_stream_failure_incoming_publish_listener_type_mismatch311(self):
        self._do_mqtt311_test(lambda protocol_client: self._do_create_stream_failure_test(
            protocol_client, lambda options: _type_mismatch_incoming_publish_listener(options)))


if __name__ == 'main':
    unittest.main()
