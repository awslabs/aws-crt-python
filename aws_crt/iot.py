# Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

from aws_crt import io, mqtt

import sys
import threading

DROP_OLDEST = 0
DROP_NEWEST = 1

class Message(object):
    __slots__ = ['topic', 'payload']

    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload

class AWSIoTMQTTClient(object):

    def __init__(self, clientID, useWebsocket=False, cleanSession=True):
        """

        The client class that connects to and accesses AWS IoT over MQTT v3.1/3.1.1.

        The following connection types are available:

        - TLSv1.2 Mutual Authentication

        X.509 certificate-based secured MQTT connection to AWS IoT

        - Websocket SigV4

        IAM credential-based secured MQTT connection over Websocket to AWS IoT

        It provides basic synchronous MQTT operations in the classic MQTT publish-subscribe
        model, along with configurations of on-top features:

        - Auto reconnect/resubscribe

        - Progressive reconnect backoff

        - Offline publish requests queueing with draining

        **Syntax**

        .. code:: python

          import AWSIoTPythonSDK.MQTTLib as AWSIoTPyMQTT

          # Create an AWS IoT MQTT Client using TLSv1.2 Mutual Authentication
          myAWSIoTMQTTClient = AWSIoTPyMQTT.AWSIoTMQTTClient("testIoTPySDK")
          # Create an AWS IoT MQTT Client using Websocket SigV4
          myAWSIoTMQTTClient = AWSIoTPyMQTT.AWSIoTMQTTClient("testIoTPySDK", useWebsocket=True)

        **Parameters**

        *clientID* - String that denotes the client identifier used to connect to AWS IoT.
        If empty string were provided, client id for this connection will be randomly generated
        n server side.

        *protocolType* - MQTT version in use for this connection. Could be :code:`AWSIoTPythonSDK.MQTTLib.MQTTv3_1` or :code:`AWSIoTPythonSDK.MQTTLib.MQTTv3_1_1`

        *useWebsocket* - Boolean that denotes enabling MQTT over Websocket SigV4 or not.

        **Returns**

        :code:`AWSIoTPythonSDK.MQTTLib.AWSIoTMQTTClient` object

        """
        assert(not useWebsocket)
        self._cleanSession = cleanSession
        self._useWebsocket = useWebsocket
        self._alpnProtocol = None

        self._username = None
        self._password = None

        self._elg = io.EventLoopGroup(1)
        self._bootstrap = io.ClientBootstrap(self._elg)
        self._tls_ctx_options = None

        self._client = mqtt.Client(self._bootstrap)
        self._connection = mqtt.Connection(self._client, clientID)

    # Configuration APIs
    def configureLastWill(self, topic, payload, QoS, retain=False):
        """
        **Description**

        Used to configure the last will topic, payload and QoS of the client. Should be called before connect.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.configureLastWill("last/Will/Topic", "lastWillPayload", 0)

        **Parameters**

        *topic* - Topic name that last will publishes to.

        *payload* - Payload to publish for last will.

        *QoS* - Quality of Service. Could be 0 or 1.

        **Returns**

        None

        """
        self._will = mqtt.Will(topic, QoS, payload, retain)

    def clearLastWill(self):
        """
        **Description**

        Used to clear the last will configuration that is previously set through configureLastWill.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.clearLastWill()

        **Parameter**

        None

        **Returns**

        None

        """
        self._will = None

    def configureEndpoint(self, hostName, portNumber):
        """
        **Description**

        Used to configure the host name and port number the client tries to connect to. Should be called
        before connect.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.configureEndpoint("random.iot.region.amazonaws.com", 8883)

        **Parameters**

        *hostName* - String that denotes the host name of the user-specific AWS IoT endpoint.

        *portNumber* - Integer that denotes the port number to connect to. Could be :code:`8883` for
        TLSv1.2 Mutual Authentication or :code:`443` for Websocket SigV4 and TLSv1.2 Mutual Authentication
        with ALPN extension.

        **Returns**

        None

        """
        self._hostName = hostName
        self._portNumber = portNumber

    def configureIAMCredentials(self, AWSAccessKeyID, AWSSecretAccessKey, AWSSessionToken=""):
        """
        **Description**

        Used to configure/update the custom IAM credentials for Websocket SigV4 connection to
        AWS IoT. Should be called before connect.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.configureIAMCredentials(obtainedAccessKeyID, obtainedSecretAccessKey, obtainedSessionToken)

        .. note::

          Hard-coding credentials into custom script is NOT recommended. Please use AWS Cognito identity service
          or other credential provider.

        **Parameters**

        *AWSAccessKeyID* - AWS Access Key Id from user-specific IAM credentials.

        *AWSSecretAccessKey* - AWS Secret Access Key from user-specific IAM credentials.

        *AWSSessionToken* - AWS Session Token for temporary authentication from STS.

        **Returns**

        None

        """
        raise NotImplementedError()

    def configureCredentials(self, CAFilePath, KeyPath="", CertificatePath=""):  # Should be good for MutualAuth certs config and Websocket rootCA config
        """
        **Description**

        Used to configure the rootCA, private key and certificate files. Should be called before connect.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.configureCredentials("PATH/TO/ROOT_CA", "PATH/TO/PRIVATE_KEY", "PATH/TO/CERTIFICATE")

        **Parameters**

        *CAFilePath* - Path to read the root CA file. Required for all connection types.

        *KeyPath* - Path to read the private key. Required for X.509 certificate based connection.

        *CertificatePath* - Path to read the certificate. Required for X.509 certificate based connection.

        **Returns**

        None

        """
        self._tls_ctx_options = io.TlsContextOptions.create_client_with_mtls(CertificatePath, KeyPath)
        self._tls_ctx_options.ca_file = CAFilePath

    def configureAutoReconnectBackoffTime(self, baseReconnectQuietTimeSecond, maxReconnectQuietTimeSecond, stableConnectionTimeSecond):
        """
        **Description**

        Used to configure the auto-reconnect backoff timing. Should be called before connect.

        **Syntax**

        .. code:: python

          # Configure the auto-reconnect backoff to start with 1 second and use 128 seconds as a maximum back off time.
          # Connection over 20 seconds is considered stable and will reset the back off time back to its base.
          myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 128, 20)

        **Parameters**

        *baseReconnectQuietTimeSecond* - The initial back off time to start with, in seconds.
        Should be less than the stableConnectionTime.

        *maxReconnectQuietTimeSecond* - The maximum back off time, in seconds.

        *stableConnectionTimeSecond* - The number of seconds for a connection to last to be considered as stable.
        Back off time will be reset to base once the connection is stable.

        **Returns**

        None

        """
        raise NotImplementedError()

    def configureOfflinePublishQueueing(self, queueSize, dropBehavior=DROP_NEWEST):
        """
        **Description**

        Used to configure the queue size and drop behavior for the offline requests queueing. Should be
        called before connect. Queueable offline requests include publish, subscribe and unsubscribe.

        **Syntax**

        .. code:: python

          import AWSIoTPythonSDK.MQTTLib as AWSIoTPyMQTT

          # Configure the offline queue for publish requests to be 20 in size and drop the oldest
           request when the queue is full.
          myAWSIoTMQTTClient.configureOfflinePublishQueueing(20, AWSIoTPyMQTT.DROP_OLDEST)

        **Parameters**

        *queueSize* - Size of the queue for offline publish requests queueing.
         If set to 0, the queue is disabled. If set to -1, the queue size is set to be infinite.

        *dropBehavior* - the type of drop behavior when the queue is full.
         Could be :code:`AWSIoTPythonSDK.core.util.enums.DropBehaviorTypes.DROP_OLDEST` or
         :code:`AWSIoTPythonSDK.core.util.enums.DropBehaviorTypes.DROP_NEWEST`.

        **Returns**

        None

        """
        raise NotImplementedError()

    def configureDrainingFrequency(self, frequencyInHz):
        """
        **Description**

        Used to configure the draining speed to clear up the queued requests when the connection is back.
        Should be called before connect.

        **Syntax**

        .. code:: python

          # Configure the draining speed to be 2 requests/second
          myAWSIoTMQTTClient.configureDrainingFrequency(2)

        .. note::

          Make sure the draining speed is fast enough and faster than the publish rate. Slow draining
          could result in inifinite draining process.

        **Parameters**

        *frequencyInHz* - The draining speed to clear the queued requests, in requests/second.

        **Returns**

        None

        """
        # self._mqtt_core.configure_draining_interval_sec(1/float(frequencyInHz))
        raise NotImplementedError()

    def configureConnectDisconnectTimeout(self, timeoutSecond):
        """
        **Description**

        Used to configure the time in seconds to wait for a CONNACK or a disconnect to complete.
        Should be called before connect.

        **Syntax**

        .. code:: python

          # Configure connect/disconnect timeout to be 10 seconds
          myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)

        **Parameters**

        *timeoutSecond* - Time in seconds to wait for a CONNACK or a disconnect to complete.

        **Returns**

        None

        """
        raise NotImplementedError()

    def configureMQTTOperationTimeout(self, timeoutSecond):
        """
        **Description**

        Used to configure the timeout in seconds for MQTT QoS 1 publish, subscribe and unsubscribe.
        Should be called before connect.

        **Syntax**

        .. code:: python

          # Configure MQTT operation timeout to be 5 seconds
          myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)

        **Parameters**

        *timeoutSecond* - Time in seconds to wait for a PUBACK/SUBACK/UNSUBACK.

        **Returns**

        None

        """
        raise NotImplementedError()

    def configureUsernamePassword(self, username, password=None):
        """
        **Description**

        Used to configure the username and password used in CONNECT packet.

        **Syntax**

        .. code:: python

          # Configure user name and password
          myAWSIoTMQTTClient.configureUsernamePassword("myUsername", "myPassword")

        **Parameters**

        *username* - Username used in the username field of CONNECT packet.

        *password* - Password used in the password field of CONNECT packet.

        **Returns**

        None

        """
        self._username = username
        self._password = password

    def enableMetricsCollection(self):
        """
        **Description**

        Used to enable SDK metrics collection. Username field in CONNECT packet will be used to append the SDK name
        and SDK version in use and communicate to AWS IoT cloud. This metrics collection is enabled by default.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.enableMetricsCollection()

        **Parameters**

        None

        **Returns**

        None

        """
        raise NotImplementedError()

    def disableMetricsCollection(self):
        """
        **Description**

        Used to disable SDK metrics collection.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.disableMetricsCollection()

        **Parameters**

        None

        **Returns**

        None

        """
        raise NotImplementedError()

    # MQTT functionality APIs
    def connect(self, keepAliveIntervalSecond=600):
        """
        **Description**

        Connect to AWS IoT, with user-specific keepalive interval configuration.

        **Syntax**

        .. code:: python

          # Connect to AWS IoT with default keepalive set to 600 seconds
          myAWSIoTMQTTClient.connect()
          # Connect to AWS IoT with keepalive interval set to 1200 seconds
          myAWSIoTMQTTClient.connect(1200)

        **Parameters**

        *keepAliveIntervalSecond* - Time in seconds for interval of sending MQTT ping request.
        Default set to 600 seconds.

        **Returns**

        True if the connect attempt succeeded. False if failed.

        """

        connected = threading.Event()

        def _onConnectWrapper(return_code, session_present):
            nonlocal connected
            self.onOnline()
            connected.set()

        def _onDisconnectWrapper(return_code):
            return self.onOffline()

        if self._tls_ctx_options:
            if self._portNumber == 443 and not self._useWebsocket:
                self._tls_ctx_options.alpn_list = "x-amzn-mqtt-ca"

            self._client.tls_ctx = io.ClientTlsContext(self._tls_ctx_options)

        self._connection.connect(
            host_name=self._hostName,
            port=self._portNumber,
            alpn=self._alpnProtocol,
            keep_alive=keepAliveIntervalSecond,
            on_connect=_onConnectWrapper,
            on_disconnect=_onDisconnectWrapper,
            will=self._will,
            username=self._username,
            password=self._password,
        )

        connected.wait()

        return True

    def connectAsync(self, keepAliveIntervalSecond=600, ackCallback=None):
        """
        **Description**

        Connect asynchronously to AWS IoT, with user-specific keepalive interval configuration and CONNACK callback.

        **Syntax**

        .. code:: python

          # Connect to AWS IoT with default keepalive set to 600 seconds and a custom CONNACK callback
          myAWSIoTMQTTClient.connectAsync(ackCallback=my_connack_callback)
          # Connect to AWS IoT with default keepalive set to 1200 seconds and a custom CONNACK callback
          myAWSIoTMQTTClient.connectAsync(keepAliveInternvalSecond=1200, ackCallback=myConnackCallback)

        **Parameters**

        *keepAliveIntervalSecond* - Time in seconds for interval of sending MQTT ping request.
        Default set to 600 seconds.

        *ackCallback* - Callback to be invoked when the client receives a CONNACK. Should be in form
        :code:`customCallback(mid, data)`, where :code:`mid` is the packet id for the connect request
        and :code:`data` is the connect result code.

        **Returns**

        Connect request packet id, for tracking purpose in the corresponding callback.

        """

        def _onConnectWrapper(return_code, session_present):
            self.onOnline()

        def _onDisconnectWrapper(return_code):
            self.onOffline()

        self._connection.connect(
            host_name=self._hostName,
            port=self._portNumber,
            alpn=self._alpnProtocol,
            keep_alive=keepAliveIntervalSecond,
            on_connect=_onConnectWrapper,
            on_disconnect=_onDisconnectWrapper,
        )

    def disconnect(self):
        """
        **Description**

        Disconnect from AWS IoT.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.disconnect()

        **Parameters**

        None

        **Returns**

        True if the disconnect attempt succeeded. False if failed.

        """

        done = threading.Event()

        old_onOffline = self.onOffline
        def new_onOffline():
            nonlocal done
            result = old_onOffline()
            done.set()
            return result
        self.onOffline = new_onOffline

        self._connection.disconnect()

        done.wait()

    def disconnectAsync(self, ackCallback=None):
        """
        **Description**

        Disconnect asynchronously to AWS IoT.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.disconnectAsync(ackCallback=myDisconnectCallback)

        **Parameters**

        *ackCallback* - Callback to be invoked when the client finishes sending disconnect and internal clean-up.
        Should be in form :code:`customCallback(mid, data)`, where :code:`mid` is the packet id for the disconnect
        request and :code:`data` is the disconnect result code.

        **Returns**

        Disconnect request packet id, for tracking purpose in the corresponding callback.

        """
        return self._connection.disconnect()

    def publish(self, topic, payload, QoS):
        """
        **Description**

        Publish a new message to the desired topic with QoS.

        **Syntax**

        .. code:: python

          # Publish a QoS0 message "myPayload" to topic "myTopic"
          myAWSIoTMQTTClient.publish("myTopic", "myPayload", 0)
          # Publish a QoS1 message "myPayloadWithQos1" to topic "myTopic/sub"
          myAWSIoTMQTTClient.publish("myTopic/sub", "myPayloadWithQos1", 1)

        **Parameters**

        *topic* - Topic name to publish to.

        *payload* - Payload to publish.

        *QoS* - Quality of Service. Could be 0 or 1.

        **Returns**

        True if the publish request has been sent to paho. False if the request did not reach paho.

        """
        done = threading.Event()

        def _puback_callback(packet_id):
            nonlocal done
            done.set()

        # Disable retain for publish by now
        self._connection.publish(topic, payload, QoS, False, _puback_callback)

        done.wait()

        return True

    def publishAsync(self, topic, payload, QoS, ackCallback=None):
        """
        **Description**

        Publish a new message asynchronously to the desired topic with QoS and PUBACK callback. Note that the ack
        callback configuration for a QoS0 publish request will be ignored as there are no PUBACK reception.

        **Syntax**

        .. code:: python

          # Publish a QoS0 message "myPayload" to topic "myTopic"
          myAWSIoTMQTTClient.publishAsync("myTopic", "myPayload", 0)
          # Publish a QoS1 message "myPayloadWithQos1" to topic "myTopic/sub", with custom PUBACK callback
          myAWSIoTMQTTClient.publishAsync("myTopic/sub", "myPayloadWithQos1", 1, ackCallback=myPubackCallback)

        **Parameters**

        *topic* - Topic name to publish to.

        *payload* - Payload to publish.

        *QoS* - Quality of Service. Could be 0 or 1.

        *ackCallback* - Callback to be invoked when the client receives a PUBACK. Should be in form
        :code:`customCallback(mid)`, where :code:`mid` is the packet id for the disconnect request.

        **Returns**

        Publish request packet id, for tracking purpose in the corresponding callback.

        """
        self._connection.publish(topic, payload, QoS, False, ackCallback)

    def subscribe(self, topic, QoS, callback):
        """
        **Description**

        Subscribe to the desired topic and register a callback.

        **Syntax**

        .. code:: python

          # Subscribe to "myTopic" with QoS0 and register a callback
          myAWSIoTMQTTClient.subscribe("myTopic", 0, customCallback)
          # Subscribe to "myTopic/#" with QoS1 and register a callback
          myAWSIoTMQTTClient.subscribe("myTopic/#", 1, customCallback)

        **Parameters**

        *topic* - Topic name or filter to subscribe to.

        *QoS* - Quality of Service. Could be 0 or 1.

        *callback* - Function to be called when a new message for the subscribed topic
        comes in. Should be in form :code:`customCallback(client, userdata, message)`, where
        :code:`message` contains :code:`topic` and :code:`payload`. Note that :code:`client` and :code:`userdata` are
        here just to be aligned with the underneath Paho callback function signature. These fields are pending to be
        deprecated and should not be depended on.

        **Returns**

        True if the subscribe attempt succeeded. False if failed.

        """
        done = threading.Event()

        def _suback_callback(packet_id, topic, qos):
            nonlocal done
            done.set()

        def _sub_callback(topic, payload):
            callback(None, None, Message(topic, payload))

        self._connection.subscribe(topic, QoS, _sub_callback, _suback_callback)

        done.wait()

        return True

    def subscribeAsync(self, topic, QoS, ackCallback=None, messageCallback=None):
        """
        **Description**

        Subscribe to the desired topic and register a message callback with SUBACK callback.

        **Syntax**

        .. code:: python

          # Subscribe to "myTopic" with QoS0, custom SUBACK callback and a message callback
          myAWSIoTMQTTClient.subscribe("myTopic", 0, ackCallback=mySubackCallback, messageCallback=customMessageCallback)
          # Subscribe to "myTopic/#" with QoS1, custom SUBACK callback and a message callback
          myAWSIoTMQTTClient.subscribe("myTopic/#", 1, ackCallback=mySubackCallback, messageCallback=customMessageCallback)

        **Parameters**

        *topic* - Topic name or filter to subscribe to.

        *QoS* - Quality of Service. Could be 0 or 1.

        *ackCallback* - Callback to be invoked when the client receives a SUBACK. Should be in form
        :code:`customCallback(mid, data)`, where :code:`mid` is the packet id for the disconnect request and
        :code:`data` is the granted QoS for this subscription.

        *messageCallback* - Function to be called when a new message for the subscribed topic
        comes in. Should be in form :code:`customCallback(client, userdata, message)`, where
        :code:`message` contains :code:`topic` and :code:`payload`. Note that :code:`client` and :code:`userdata` are
        here just to be aligned with the underneath Paho callback function signature. These fields are pending to be
        deprecated and should not be depended on.

        **Returns**

        Subscribe request packet id, for tracking purpose in the corresponding callback.

        """

        def _suback_callback(packet_id, topic, qos):
            ackCallback(packet_id, qos)

        def _sub_callback(topic, payload):
            print("GOT DAM DATA")
            messageCallback(None, None, Message(topic, payload))

        return self._connection.subscribe(topic, QoS, _sub_callback, _suback_callback)

    def unsubscribe(self, topic):
        """
        **Description**

        Unsubscribe to the desired topic.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.unsubscribe("myTopic")

        **Parameters**

        *topic* - Topic name or filter to unsubscribe to.

        **Returns**

        True if the unsubscribe attempt succeeded. False if failed.

        """
        done = threading.Event()

        def _unsuback_callback(packet_id):
            nonlocal done
            done.set()

        self._connection.unsubscribe(topic, _unsuback_callback)

        done.wait()

        return True

    def unsubscribeAsync(self, topic, ackCallback=None):
        """
        **Description**

        Unsubscribe to the desired topic with UNSUBACK callback.

        **Syntax**

        .. code:: python

          myAWSIoTMQTTClient.unsubscribe("myTopic", ackCallback=myUnsubackCallback)

        **Parameters**

        *topic* - Topic name or filter to unsubscribe to.

        *ackCallback* - Callback to be invoked when the client receives a UNSUBACK. Should be in form
        :code:`customCallback(mid)`, where :code:`mid` is the packet id for the disconnect request.

        **Returns**

        Unsubscribe request packet id, for tracking purpose in the corresponding callback.

        """
        return self._connection.unsubscribe(topic, ackCallback)

    def onOnline(self):
        """
        **Description**

        Callback that gets called when the client is online. The callback registration should happen before calling
        connect/connectAsync.

        **Syntax**

        .. code:: python

          # Register an onOnline callback
          myAWSIoTMQTTClient.onOnline = myOnOnlineCallback

        **Parameters**

        None

        **Returns**

        None

        """
        pass

    def onOffline(self):
        """
        **Description**

        Callback that gets called when the client is offline. The callback registration should happen before calling
        connect/connectAsync.

        **Syntax**

        .. code:: python

          # Register an onOffline callback
          myAWSIoTMQTTClient.onOffline = myOnOfflineCallback

        **Parameters**

        None

        **Returns**

        None

        """
        return False

    def onMessage(self, message):
        """
        **Description**

        Callback that gets called when the client receives a new message. The callback registration should happen before
        calling connect/connectAsync. This callback, if present, will always be triggered regardless of whether there is
        any message callback registered upon subscribe API call. It is for the purpose to aggregating the processing of
        received messages in one function.

        **Syntax**

        .. code:: python

          # Register an onMessage callback
          myAWSIoTMQTTClient.onMessage = myOnMessageCallback

        **Parameters**

        *message* - Received MQTT message. It contains the source topic as :code:`message.topic`, and the payload as
        :code:`message.payload`.

        **Returns**

        None

        """
        pass
