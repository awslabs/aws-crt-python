# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from concurrent.futures import Future
from awscrt import mqtt5, exceptions, http
import pathlib
import os
import enum
import uuid
import time
import random
import sys


AuthType = enum.Enum('AuthType', ['DIRECT',
                                  'DIRECT_BASIC_AUTH',
                                  'DIRECT_TLS',
                                  'DIRECT_PROXY',
                                  'WS',
                                  'WS_BASIC_AUTH',
                                  'WS_TLS',
                                  'WS_PROXY',
                                  'CANARY'])


def create_client_id():
    return f"aws-crt-python-canary-test-{uuid.uuid4()}"


def _get_env(name):
    val = os.environ.get(name)
    if not val:
        raise Exception(name + "environment variable required for canary")
    return val


TIMEOUT = 100.0
endpoint = _get_env("ENDPOINT")
port = _get_env("AWS_TEST_MQTT5_DIRECT_MQTT_PORT")
seconds = _get_env("CANARY_DURATION")
threads = _get_env("CANARY_THREADS")
tps = _get_env("CANARY_TPS")
client_count = _get_env("CANARY_CLIENT_COUNT")
log_level = _get_env("CANARY_LOG_LEVEL")


class CanaryCore():
    def __init__(self):
        # Stats
        self.stat_publishes_received = 0
        self.stat_subscribes_attempted = 0
        self.stat_subscribes_succeeded = 0
        self.stat_subscribes_failed = 0
        self.stat_unsubscribes_attempted = 0
        self.stat_unsubscribes_succeeded = 0
        self.stat_unsubscribes_failed = 0
        self.stat_publishes_attempted = 0
        self.stat_publishes_succeeded = 0
        self.stat_publishes_failed = 0

        self.future_connection_success = None
        self.future_stopped = None

        self.subscriptions = []

    def ws_handshake_transform(self, transform_args):
        transform_args.set_done()

    def on_publish_received(self, publish_received_data: mqtt5.PublishReceivedData):
        self.stat_publishes_received += 1

    def on_lifecycle_stopped(self, lifecycle_stopped: mqtt5.LifecycleStoppedData):
        if self.future_stopped:
            if self.future_stopped.done():
                pass
            else:
                self.future_stopped.set_result(None)

    def on_lifecycle_attempting_connect(self, lifecycle_attempting_connect: mqtt5.LifecycleAttemptingConnectData):
        pass

    def on_lifecycle_connection_success(self, lifecycle_connection_success: mqtt5.LifecycleConnectSuccessData):
        if self.future_connection_success:
            if self.future_connection_success.done():
                pass
            else:
                self.future_connection_success.set_result(lifecycle_connection_success)

    def on_lifecycle_connection_failure(self, lifecycle_connection_failure: mqtt5.LifecycleConnectFailureData):
        pass

    def on_lifecycle_disconnection(self, lifecycle_disconnect_data: mqtt5.LifecycleDisconnectData):
        pass


class CanaryClient():
    user_properties = []
    user_properties.append(mqtt5.UserProperty(name="name1", value="value1"))
    user_properties.append(mqtt5.UserProperty(name="name2", value="value2"))

    def __init__(self, auth_type=AuthType.CANARY):
        self.client_id = create_client_id()
        self.canary_core = CanaryCore()
        self.client = self._create_client(canary_core=self.canary_core)
        self.stopped = True

    def _create_client(self,
                       client_options: mqtt5.ClientOptions = None,
                       canary_core: CanaryCore = None):

        if client_options is None:
            client_options = mqtt5.ClientOptions(endpoint, port)

        if client_options.connect_options is None:
            client_options.connect_options = mqtt5.ConnectPacket()
            client_options.connect_options.client_id = create_client_id()

        client_options.host_name = endpoint
        client_options.port = int(port)

        if canary_core is not None:
            client_options.on_publish_callback_fn = canary_core.on_publish_received
            client_options.on_lifecycle_event_stopped_fn = canary_core.on_lifecycle_stopped
            client_options.on_lifecycle_event_attempting_connect_fn = canary_core.on_lifecycle_attempting_connect
            client_options.on_lifecycle_event_connection_success_fn = canary_core.on_lifecycle_connection_success
            client_options.on_lifecycle_event_connection_failure_fn = canary_core.on_lifecycle_connection_failure
            client_options.on_lifecycle_event_disconnection_fn = canary_core.on_lifecycle_disconnection

        client = mqtt5.Client(client_options)
        return client

    def random_operation(self):
        time.sleep(0.05)
        operation = random.randint(0, 100)

        if self.stopped:
            self.start()
        elif operation < 10:
            self.subscribe()
        elif operation < 20:
            self.unsubscribe()
        elif operation < 98:
            self.publish()
        else:
            if not self.stopped:
                self.stop()

    def start(self):
        if not self.stopped:
            return

        future_connection_success = Future()
        self.canary_core.future_connection_success = future_connection_success
        self.client.start()
        future_connection_success.result(TIMEOUT)
        self.stopped = False

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        future_stopped = Future()
        self.canary_core.future_stopped = future_stopped
        self.client.stop()
        future_stopped.result(TIMEOUT)

    def publish(self):
        self.canary_core.stat_publishes_attempted += 1

        if len(self.canary_core.subscriptions) > 0:
            topic_filter = self.canary_core.subscriptions[0]
        else:
            topic_filter = str(time.time()) + self.client_id

        publish_packet = mqtt5.PublishPacket(
            topic=topic_filter,
            qos=random.randint(0, 1),
            payload=bytearray(os.urandom(random.randint(0, 10000)))
        )

        if random.getrandbits(1):
            publish_packet.user_properties = self.user_properties

        try:
            self.client.publish(publish_packet=publish_packet)
            self.canary_core.stat_publishes_succeeded += 1
        except BaseException:
            self.canary_core.stat_publishes_failed += 1

    def subscribe(self, topic_filter: str = None, qos: int = 1):
        self.canary_core.stat_subscribes_attempted += 1
        if topic_filter is None:
            topic_filter = str(time.time()) + self.client_id

        self.canary_core.subscriptions.append(topic_filter)

        subscribe_packet = mqtt5.SubscribePacket(subscriptions=[mqtt5.Subscription(topic_filter=topic_filter, qos=qos)])

        try:
            self.client.subscribe(subscribe_packet=subscribe_packet)
            self.canary_core.stat_subscribes_succeeded += 1
        except BaseException:
            self.canary_core.stat_subscribes_failed += 1

    def unsubscribe(self):
        if len(self.canary_core.subscriptions) < 1:
            return

        self.canary_core.stat_unsubscribes_attempted += 1
        unsubscribe_packet = mqtt5.UnsubscribePacket(topic_filters=[self.canary_core.subscriptions.pop()])

        try:
            self.client.unsubscribe(unsubscribe_packet=unsubscribe_packet)
            self.canary_core.stat_unsubscribes_succeeded += 1
        except BaseException:
            self.canary_core.stat_unsubscribes_failed += 1

    def print_stats(self):
        print(f"""\n
Client Stats:
    publishes_received:     {self.canary_core.stat_publishes_received}

    subscribes_attempted:   {self.canary_core.stat_subscribes_attempted}
    subscribes_succeeded:   {self.canary_core.stat_subscribes_succeeded}
    subscribes_failed:      {self.canary_core.stat_subscribes_failed}

    unsubscribes_attempted: {self.canary_core.stat_unsubscribes_attempted}
    unsubscribes_succeeded: {self.canary_core.stat_unsubscribes_succeeded}
    unsubscribes_failed:    {self.canary_core.stat_unsubscribes_failed}

    publishes_attempted:    {self.canary_core.stat_publishes_attempted}
    publishes_succeeded:    {self.canary_core.stat_publishes_succeeded}
    publishes_failed:       {self.canary_core.stat_publishes_failed}""", file=sys.stdout)


if __name__ == '__main__':
    client = CanaryClient()
    time_end = time.time() + float(seconds)
    tpsdelay = 1.0 / float(tps)
    time_next_operation = time.time()

    print(f"""\n
    Canary running for {seconds} seconds
    TPS: {tps} : {tpsdelay}
    Clients: {client_count}
    """, file=sys.stdout)

    clients = []
    for i in range(int(client_count)):
        clients.append(CanaryClient())

    for client in clients:
        client.start()

    time.sleep(0.1)
    for client in clients:
        client.subscribe()

    while time.time() < time_end:
        if time.time() >= time_next_operation:
            time_next_operation += tpsdelay
            for client in clients:
                client.random_operation()

    time.sleep(0.1)
    for client in clients:
        client.stop()

    time.sleep(0.1)
    for client in clients:
        client.print_stats()

    time.sleep(0.1)

    for client in clients:
        del client

    time.sleep(0.1)
