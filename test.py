from aws_crt_python import io, mqtt, iot
from AWSIoTPythonSDK import MQTTLib
import time, threading
from timeit import default_timer as timer

messages_recieved = 0
messages_recieved_cv = threading.Condition()

def iot_on_connect():
    print("iot connected")

def iot_on_message(client, userdata, message):
    global messages_recieved

    with messages_recieved_cv:
        messages_recieved += 1
        messages_recieved_cv.notify()

def iot_on_disconnect():
    print("iot disconnected")

client = iot.AWSIoTMQTTClient
# client = MQTTLib.AWSIoTMQTTClient

if io.is_alpn_available():
    port = 443
else:
    port = 8883

iot_client = client("coldens iot client")
iot_client.onOnline = iot_on_connect
iot_client.onOffline = iot_on_disconnect
iot_client.configureEndpoint("a1ba5f1mpna9k5-ats.iot.us-east-1.amazonaws.com", port)
iot_client.configureCredentials("AmazonRootCA1.pem", "9f0631f03a-private.pem.key", "9f0631f03a-certificate.pem.crt")

print("connecting...")
iot_client.connect()

# MQTT subscribes
print("subscribing...")
iot_client.subscribe("a", 1, iot_on_message)

print("publishing...")

begin_publish = timer()

num_publishes = 100
for i in range(0, num_publishes):
    # Publish data to the mqtt client
    iot_client.publishAsync("a", "REQUEST", 1)

end_publish = timer()

with messages_recieved_cv:
    while messages_recieved < num_publishes:
        messages_recieved_cv.wait()

pubacks_gotten = timer()

print("unsubscribing...")
iot_client.unsubscribe("a")

print("disconnecting...")

iot_client.disconnect()

print("Publish time: {}\nTotal time: {}".format(end_publish - begin_publish, pubacks_gotten - begin_publish))

print("exiting...")
