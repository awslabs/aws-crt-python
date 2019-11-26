# Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

from __future__ import print_function

import argparse
from awscrt import io, mqtt
from awscrt.io import LogLevel
import threading
import uuid

TIMEOUT = 5 # seconds given to each step of the test before giving up
UNIQUE_ID = str(uuid.uuid4()) # prevent simultaneously-running tests from interfering with each other
CLIENT_ID = 'test_pubsub_' + UNIQUE_ID
TOPIC = 'test/pubsub/' + UNIQUE_ID
MESSAGE = 'test message ' + UNIQUE_ID

parser = argparse.ArgumentParser()
parser.add_argument('--endpoint', required=True, help="Connect to this endpoint (aka host-name)")
parser.add_argument('--port', type=int, help="Override default connection port")
parser.add_argument('--cert', help="File path to your client certificate, in PEM format")
parser.add_argument('--key', help="File path to your private key, in PEM format")
parser.add_argument('--root-ca', help="File path to root certificate authority, in PEM format")

io.init_logging(LogLevel.Trace, 'stderr')

def on_connection_interrupted(connection, error):
    print("Connection has been interrupted with error", error)

def on_connection_resumed(connection, return_code, session_present):
    print("Connection has been resumed with return code", return_code, "and session present:", session_present)

    if not session_present:
        print("Resubscribing to existing topics")
        resubscribe_future, packet_id = connection.resubscribe_existing_topics()

        def on_resubscribe_complete(resubscribe_future):
            try:
                resubscribe_results = resubscribe_future.result()
                print("Resubscribe results:", resubscribe_results)
                assert(resubscribe_results['packet_id'] == packet_id)
                for (topic, qos) in resubscribe_results['topics']:
                    assert(qos is not None)
            except Exception as e:
                print("Resubscribe failure:", e)
                exit(-1)

        resubscribe_future.add_done_callback(on_resubscribe_complete)

receive_results = {}
receive_event = threading.Event()
def on_receive_message(topic, message):
    receive_results.update(locals())
    receive_event.set()

# Run
args = parser.parse_args()
event_loop_group = io.EventLoopGroup(1)
host_resolver = io.DefaultHostResolver(event_loop_group)
client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

tls_options = None
if args.cert or args.key or args.root_ca:
    if args.cert:
        assert args.key
        tls_options = io.TlsContextOptions.create_client_with_mtls_from_path(args.cert, args.key)
    else:
        tls_options = io.TlsContextOptions()

    if args.root_ca:
        with open(args.root_ca, mode='rb') as ca:
            rootca = ca.read()
        tls_options.override_default_trust_store(rootca)

if args.port:
    port = args.port
elif io.is_alpn_available():
    port = 443
    if tls_options:
        tls_options.alpn_list = ['x-amzn-mqtt-ca']
else:
    port = 8883

tls_context = io.ClientTlsContext(tls_options) if tls_options else None
mqtt_client = mqtt.Client(client_bootstrap, tls_context)

# Connect
print("Connecting to {}:{} with client-id:{}".format(args.endpoint, port, CLIENT_ID))
mqtt_connection = mqtt.Connection(
    client=mqtt_client,
    host_name=args.endpoint,
    port=port,
    client_id=CLIENT_ID,
    on_connection_interrupted=on_connection_interrupted,
    on_connection_resumed=on_connection_resumed)

connect_results = mqtt_connection.connect().result(TIMEOUT)
assert(connect_results['session_present'] == False)

# Subscribe
print("Subscribing to:", TOPIC)
qos = mqtt.QoS.AT_LEAST_ONCE
subscribe_future, subscribe_packet_id = mqtt_connection.subscribe(
    topic=TOPIC,
    qos=qos,
    callback=on_receive_message)
subscribe_results = subscribe_future.result(TIMEOUT)
assert(subscribe_results['packet_id'] == subscribe_packet_id)
assert(subscribe_results['topic'] == TOPIC)
print(subscribe_results)
assert(subscribe_results['qos'] == qos)

# Publish
print("Publishing to '{}': {}".format(TOPIC, MESSAGE))
publish_future, publish_packet_id = mqtt_connection.publish(
    topic=TOPIC,
    payload=MESSAGE,
    qos=mqtt.QoS.AT_LEAST_ONCE)
publish_results = publish_future.result(TIMEOUT)
assert(publish_results['packet_id'] == publish_packet_id)

# Receive Message
print("Waiting to receive messsage")
assert(receive_event.wait(TIMEOUT))
assert(receive_results['topic'] == TOPIC)
assert(receive_results['message'].decode() == MESSAGE)

# Unsubscribe
print("Unsubscribing from topic")
unsubscribe_future, unsubscribe_packet_id = mqtt_connection.unsubscribe(TOPIC)
unsubscribe_results = unsubscribe_future.result(TIMEOUT)
assert(unsubscribe_results['packet_id'] == unsubscribe_packet_id)

# Disconnect
print("Disconnecting")
mqtt_connection.disconnect().result(TIMEOUT)

# Done
print("Test Success")
