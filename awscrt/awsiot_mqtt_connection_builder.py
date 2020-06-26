"""
Builder functions to create a awscrt.mqtt.Connection, configured for use with AWS IoT.
The following arguments are common to all builder functions:

Required Arguments:

    endpoint (str): Host name of AWS IoT server.

    client_bootstrap (awscrt.io.ClientBootstrap): Client bootstrap used to establish connection.

    client_id (str): ID to place in CONNECT packet. Must be unique across all devices/clients.
            If an ID is already in use, the other client will be disconnected.

Optional Arguments:

    on_connection_interrupted (function): Callback with signature:
            (awscrt.mqtt.Connection, awscrt.exceptions.AwsCrtError) -> None
            Invoked when the MQTT connection is lost.
            The MQTT client will automatically attempt to reconnect.

    on_connection_resumed (function): Callback with signature:
            (awscrt.mqtt.Connection, awscrt.mqtt.ConnectReturnCode, session_present: bool) -> None
            Invoked when the MQTT connection is automatically resumed.

    clean_session (bool): Whether or not to start a clean session with each reconnect.
            Default is true, the server will forget all subscriptions with each reconnect.
            Set False to request that the server resume an existing session
            or start a new session that may be resumed after a connection loss.
            The `session_present` bool in the connection callback informs
            whether an existing session was successfully resumed.
            If an existing session is resumed, the server remembers previous subscriptions
            and sends mesages (with QoS1 or higher) that were published while the client was offline.

    reconnect_min_timeout_secs (int): Minimum time to wait between reconnect attempts.
        Wait starts at min and doubles with each attempt until max is reached.

    reconnect_max_timeout_secs (int): Maximum time to wait between reconnect attempts.
        Wait starts at min and doubles with each attempt until max is reached.

    keep_alive_secs (int): The keep alive value, in seconds, to send in CONNECT packet.
                A PING will automatically be sent at this interval.
                The server will assume the connection is lost if no PING is received after 1.5X this value.
                Default is 1200sec (20 minutes). This duration must be longer than ping_timeout_ms.

    ping_timeout_ms (int): Milliseconds to wait for ping response before client assumes
                the connection is invalid and attempts to reconnect.
                Default is 3000ms (3 seconds). This duration must be shorter than keep_alive_secs.
                Alternatively, TCP keep-alive may accomplish this in a more efficient (low-power) scenario,
                but keep-alive options may not work the same way on every platform and OS version.

    will (awscrt.mqtt.Will): Will to send with CONNECT packet. The will is
                published by the server when its connection to the client
                is unexpectedly lost.

    username (str): Username to connect with.

    password (str): Password to connect with.

    port (int): Override default server port.
            Default port is 443 if system supports ALPN or websockets are being used.
            Otherwise, default port is 8883.

    tcp_connect_timeout_ms (int): Milliseconds to wait for TCP connect response. Default is 5000ms (5 seconds).

    tcp_keep_alive (bool): Whether to use TCP keep-alive. Default is False. If True, periodically transmit messages
            for detecting a disconnected peer.

    tcp_keep_alive_interval_secs (int): Interval, in seconds, for TCP keep-alive.

    tcp_keep_alive_timeout_secs (int): Timeout, in seconds, for TCP keep-alive.

    tcp_keep_alive_max_probes (int): Number of probes allowed to fail before the connection is considered lost.

    ca_filepath (str): Override default trust store with CA certificates from this PEM formatted file.

    ca_dirpath (str): Override default trust store with CA certificates loaded from this directory (Unix only).

    ca_bytes (bytes): Override default trust store with CA certificates from these PEM formatted bytes.

    enable_metrics_collection (bool): Whether to send the SDK version number in the CONNECT packet. Default is True.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt.auth
import awscrt.io
import awscrt.mqtt


def _check_required_kwargs(**kwargs):
    for required in ['client_bootstrap', 'endpoint', 'client_id']:
        if not kwargs.get(required):
            raise TypeError("Builder needs keyword-only argument '{}'".format(required))


_metrics_str = None


def _get_metrics_str():
    global _metrics_str
    if _metrics_str is None:
        try:
            import pkg_resources
            try:
                version = pkg_resources.get_distribution("awscrt").version
                _metrics_str = "?SDK=PythonV2&Version={}".format(version)
            except pkg_resources.DistributionNotFound:
                _metrics_str = "?SDK=PythonV2&Version=dev"
        except BaseException:
            _metrics_str = ""

    return _metrics_str


def _builder(
        tls_ctx_options,
        use_websockets=False,
        websocket_handshake_transform=None,
        websocket_proxy_options=None,
        **kwargs):

    ca_bytes = kwargs.get('ca_bytes')
    ca_filepath = kwargs.get('ca_filepath')
    ca_dirpath = kwargs.get('ca_dirpath')
    if ca_bytes:
        tls_ctx_options.override_default_trust_store(ca_bytes)
    elif ca_filepath or ca_dirpath:
        tls_ctx_options.override_default_trust_store_from_path(ca_dirpath, ca_filepath)

    if use_websockets:
        port = 443
        if awscrt.io.is_alpn_available():
            tls_ctx_options.alpn_list = ['http/1.1']
    else:
        port = 8883
        if awscrt.io.is_alpn_available():
            port = 443
            tls_ctx_options.alpn_list = ['x-amzn-mqtt-ca']

    port = kwargs.get('port', port)

    socket_options = awscrt.io.SocketOptions()
    socket_options.connect_timeout_ms = kwargs.get('tcp_connect_timeout_ms', 5000)
    # These have been inconsistent between keepalive/keep_alive. Resolve both for now to ease transition.
    socket_options.keep_alive = kwargs.get('tcp_keep_alive', kwargs.get('tcp_keepalive', False))
    socket_options.keep_alive_timeout_secs = kwargs.get(
        'tcp_keep_alive_timeout_secs', kwargs.get(
            'tcp_keepalive_timeout_secs', 0))
    socket_options.keep_alive_interval_secs = kwargs.get(
        'tcp_keep_alive_interval_secs', kwargs.get(
            'tcp_keepalive_interval_secs', 0))
    socket_options.keep_alive_max_probes = kwargs.get(
        'tcp_keep_alive_max_probes', kwargs.get(
            'tcp_keepalive_max_probes', 0))

    username = kwargs.get('username', '')
    if kwargs.get('enable_metrics_collection', True):
        username += _get_metrics_str()

    client_bootstrap = kwargs.get('client_bootstrap')
    tls_ctx = awscrt.io.ClientTlsContext(tls_ctx_options)
    mqtt_client = awscrt.mqtt.Client(client_bootstrap, tls_ctx)

    return awscrt.mqtt.Connection(
        client=mqtt_client,
        on_connection_interrupted=kwargs.get('on_connection_interrupted'),
        on_connection_resumed=kwargs.get('on_connection_resumed'),
        client_id=kwargs.get('client_id'),
        host_name=kwargs.get('endpoint'),
        port=port,
        clean_session=kwargs.get('clean_session', False),
        reconnect_min_timeout_secs=kwargs.get('reconnect_min_timeout_secs', 5),
        reconnect_max_timeout_secs=kwargs.get('reconnect_max_timeout_secs', 60),
        keep_alive_secs=kwargs.get('keep_alive_secs', 1200),
        ping_timeout_ms=kwargs.get('ping_timeout_ms', 3000),
        will=kwargs.get('will'),
        username=username,
        password=kwargs.get('password'),
        socket_options=socket_options,
        use_websockets=use_websockets,
        websocket_handshake_transform=websocket_handshake_transform,
        websocket_proxy_options=websocket_proxy_options,
    )


def mtls_from_path(cert_filepath, pri_key_filepath, **kwargs):
    """
    This builder creates an awscrt.mqtt.Connection, configured for an mTLS MQTT connection to AWS IoT.
    TLS arguments are passed as filepaths.

    Arguments:
        cert_filepath (str): Path to certificate file.

        pri_key_filepath (str): Path to private key file.

        All other required and optional arguments are explained in this module's docs.
    """
    _check_required_kwargs(**kwargs)
    tls_ctx_options = awscrt.io.TlsContextOptions.create_client_with_mtls_from_path(cert_filepath, pri_key_filepath)
    return _builder(tls_ctx_options, **kwargs)


def mtls_from_bytes(cert_bytes, pri_key_bytes, **kwargs):
    """
    This builder creates an awscrt.mqtt.Connection, configured for an mTLS MQTT connection to AWS IoT.
    TLS arguments are passed as in-memory bytes.

    Arguments:
        cert_bytes (bytes): Certificate file.

        pri_key_bytes (bytes): Private key.

        All other required and optional arguments are explained in this module's docs.
    """
    _check_required_kwargs(**kwargs)
    tls_ctx_options = awscrt.io.TlsContextOptions.create_client_with_mtls(cert_bytes, pri_key_bytes)
    return _builder(tls_ctx_options, **kwargs)


def websockets_with_default_aws_signing(region, credentials_provider, websocket_proxy_options=None, **kwargs):
    """
    This builder creates an awscrt.mqtt.Connection, configured for an MQTT connection over websockets to AWS IoT.
    The websocket handshake is signed using credentials from the credentials_provider.

    Arguments:
        region (str): AWS region to use when signing.

        credentials_provider (awscrt.auth.AwsCredentialsProviderBase): Source of AWS credentials to use when signing.

        websocket_proxy_options (awscrt.http.HttpProxyOptions): If specified, a proxy is used when connecting.

        All other required and optional arguments are explained in this module's docs.
    """
    _check_required_kwargs(**kwargs)

    def _sign_websocket_handshake_request(transform_args, **kwargs):
        # transform_args need to know when transform is done
        try:
            signing_config = awscrt.auth.AwsSigningConfig(
                algorithm=awscrt.auth.AwsSigningAlgorithm.V4,
                signature_type=awscrt.auth.AwsSignatureType.HTTP_REQUEST_QUERY_PARAMS,
                credentials_provider=credentials_provider,
                region=region,
                service='iotdevicegateway',
                omit_session_token=True,  # IoT is weird and does not sign X-Amz-Security-Token
            )

            signing_future = awscrt.auth.aws_sign_request(transform_args.http_request, signing_config)
            signing_future.add_done_callback(lambda x: transform_args.set_done(x.exception()))
        except Exception as e:
            transform_args.set_done(e)

    return websockets_with_custom_handshake(_sign_websocket_handshake_request, websocket_proxy_options, **kwargs)


def websockets_with_custom_handshake(websocket_handshake_transform, websocket_proxy_options=None, **kwargs):
    """
    This builder creates an awscrt.mqtt.Connection, configured for an MQTT connection over websockets,
    with a custom function to transform the websocket handshake request before it is sent to the server.

    Arguments:
        websocket_handshake_transform: Function with signature:
                (awscrt.mqtt.WebsocketHandshakeTransformArgs) -> None
                Function is called each time a websocket connection is attempted.
                The function may modify the websocket handshake request, and MUST call set_done() when complete.
                See awscrt.mqtt.WebsocketHandshakeTransformArgs for more info.

        websocket_proxy_options (awscrt.http.HttpProxyOptions): If specified, a proxy is used when connecting.

        All other required and optional arguments are explained in this module's docs.
    """
    _check_required_kwargs(**kwargs)
    tls_ctx_options = awscrt.io.TlsContextOptions()
    return _builder(tls_ctx_options=tls_ctx_options,
                    use_websockets=True,
                    websocket_handshake_transform=websocket_handshake_transform,
                    websocket_proxy_options=websocket_proxy_options,
                    **kwargs)
