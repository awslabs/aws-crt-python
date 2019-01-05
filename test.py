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

import argparse
from aws_crt import io, mqtt
import threading
import uuid

TIMEOUT = 5 # seconds given to each step of the test before giving up
UNIQUE_ID = str(uuid.uuid4()) # prevent simultaneously-running tests from interfering with each other
CLIENT_ID = 'test_pubsub_' + UNIQUE_ID
TOPIC = 'test/pubsub/' + UNIQUE_ID
MESSAGE = 'test message ' + UNIQUE_ID

parser = argparse.ArgumentParser()
parser.add_argument('--endpoint', required=True, help="Connect to this endpoint (aka host-name)")
parser.add_argument('--port', help="Override default connection port")
parser.add_argument('--cert', help="File path to your client certificate, in PEM format")
parser.add_argument('--key', help="File path to your private key, in PEM format")
parser.add_argument('--root-ca', help="File path to root certificate authority, in PEM format")

connect_results = {}
connect_event = threading.Event()
def on_connect(error_code, return_code, session_present):
    connect_results.update(locals())
    connect_event.set()

def on_connection_interrupted(error_code):
    print("Connection has been interrupted with error code", error_code)

def on_connection_resumed(return_code, session_present):
    print("Connection has been resumed with return code", return_code, "and session present:", session_present)

disconnect_results = {}
disconnect_event = threading.Event()
def on_disconnect():
    disconnect_results.update(locals())
    disconnect_event.set()
    return False

receive_results = {}
receive_event = threading.Event()
def on_receive_message(topic, message):
    receive_results.update(locals())
    receive_event.set()

subscribe_results = {}
subscribe_event = threading.Event()
def on_subscribe(packet_id, topic, qos):
    subscribe_results.update(locals())
    subscribe_event.set()

unsubscribe_results = {}
unsubscribe_event = threading.Event()
def on_unsubscribe(packet_id):
    unsubscribe_results.update(locals())
    unsubscribe_event.set()

publish_results = {}
publish_event = threading.Event()
def on_publish(packet_id):
    publish_results.update(locals())
    publish_event.set()

# Run
args = parser.parse_args()
event_loop_group = io.EventLoopGroup(1)
client_bootstrap = io.ClientBootstrap(event_loop_group)

if args.cert or args.key or args.root_ca:
    if args.cert:
        assert(args.key)
        tls_options = io.TlsContextOptions.create_client_with_mtls(args.cert, args.key)
    else:
        tls_options = io.TlsContextOptions()

    if args.root_ca:
        tls_options.override_default_trust_store(ca_path=None, ca_file=args.root_ca)

if args.port:
    port = args.port
elif io.is_alpn_available():
    port = 443
    if tls_options:
        tls_options.alpn_list='x-amzn-mqtt-ca'
else:
    port = 8883

tls_context = io.ClientTlsContext(tls_options) if tls_options else None
mqtt_client = mqtt.Client(client_bootstrap, tls_context)

# Connect
print("Connecting to {}:{} with client-id:{}".format(args.endpoint, port, CLIENT_ID))
mqtt_connection = mqtt.Connection(
    client=mqtt_client,
    client_id=CLIENT_ID,
    host_name=args.endpoint,
    port=port,
    on_connect=on_connect,
    on_connection_interrupted=on_connection_interrupted,
    on_connection_resumed=on_connection_resumed)
assert(connect_event.wait(TIMEOUT))
assert(connect_results['error_code'] == 0)
assert(connect_results['return_code'] == 0)
assert(connect_results['session_present'] == False)

# Subscribe
print("Subscribing to:", TOPIC)
qos = mqtt.QoS.AtLeastOnce
subscribe_packet_id = mqtt_connection.subscribe(
    topic=TOPIC,
    qos=qos,
    callback=on_receive_message,
    suback_callback=on_subscribe)
assert(subscribe_event.wait(TIMEOUT))
assert(subscribe_results['packet_id'] == subscribe_packet_id)
assert(subscribe_results['topic'] == TOPIC)
assert(subscribe_results['qos'] == qos)

# Publish
print("Publishing to '{}': {}".format(TOPIC, MESSAGE))
publish_packet_id = mqtt_connection.publish(
    topic=TOPIC,
    payload=MESSAGE,
    qos=mqtt.QoS.AtLeastOnce,
    puback_callback=on_publish)
assert(publish_event.wait(TIMEOUT))
assert(publish_results['packet_id'] == publish_packet_id)

# Receive Message
print("Waiting to receive messsage")
assert(receive_event.wait(TIMEOUT))
assert(receive_results['topic'] == TOPIC)
assert(receive_results['message'] == MESSAGE)

# Unsubscribe
print("Unsubscribing from topic")
unsubscribe_packet_id = mqtt_connection.unsubscribe(TOPIC, on_unsubscribe)
assert(unsubscribe_event.wait(TIMEOUT))
assert(unsubscribe_results['packet_id'] == unsubscribe_packet_id)

# Disconnect
print("Disconnecting")
mqtt_connection.disconnect(on_disconnect)
assert(disconnect_event.wait(TIMEOUT))

# Done
print("Test Success")
