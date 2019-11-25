# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import awscrt.auth
import awscrt.io
import awscrt.mqtt

"""
Required Arguments:
    endpoint
    client_bootstrap
    client_id

Optional Arguments:
    ca_filepath,
    ca_dirpath,
    ca_bytes,

    port
    on_connection_interrupted
    on_connection_resumed
    reconnect_min_timeout_secs
    reconnect_max_timeout_secs
    clean_session
    keep_alive_secs
    ping_timeout_ms
    will
    username
    password

    tcp_connect_timeout_ms: 3000 (3 seconds) by default
    tcp_keepalive
    tcp_keepalive_timeout_secs
    tcp_keepalive_interval_secs
    tcp_keepalive_max_probes

    enable_metrics_collection
"""


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
    socket_options.connect_timeout_ms = kwargs.get('tcp_connect_timeout_ms', 3000)
    socket_options.keep_alive = kwargs.get('tcp_keepalive', False)
    socket_options.keep_alive_timeout_secs = kwargs.get('tcp_keepalive_timeout_secs', 0)
    socket_options.keep_alive_interval_secs = kwargs.get('tcp_keep_alive_interval_secs', 0)
    socket_options.keep_alive_max_probes = kwargs.get('tcp_keep_alive_max_probes', 0)

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
        keep_alive_secs=kwargs.get('keep_alive_secs', 3600),
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
    _check_required_kwargs(**kwargs)
    tls_ctx_options = awscrt.io.TlsContextOptions.create_client_with_mtls_from_path(cert_filepath, pri_key_filepath)
    return _builder(tls_ctx_options, **kwargs)


def mtls_from_bytes(cert_bytes, pri_key_bytes, **kwargs):
    _check_required_kwargs(**kwargs)
    tls_ctx_options = awscrt.io.TlsContextOptions.create_client_with_mtls(cert_bytes, pri_key_bytes)
    return _builder(tls_ctx_options, **kwargs)


def websockets_with_default_aws_signing(region, credentials_provider=None, websocket_proxy_options=None, **kwargs):
    _check_required_kwargs(**kwargs)

    if credentials_provider is None:
        credentials_provider = awscrt.auth.AwsCredentialsProvider.new_default_chain(kwargs.get('client_bootstrap'))

    def _should_sign_param(name):
        blacklist = ['x-amz-date', 'x-amz-security-token']
        return not (name.lower() in blacklist)

    def _sign_websocket_handshake_request(handshake_args):
        # handshake_args need to know when transform is done
        try:
            signing_config = awscrt.auth.AwsSigningConfig(
                algorithm=awscrt.auth.AwsSigningAlgorithm.SigV4QueryParam,
                credentials_provider=credentials_provider,
                region=region,
                service='iotdevicegateway',
                should_sign_param=_should_sign_param,
                sign_body=False)

            signing_future = awscrt.auth.aws_sign_request(handshake_args.http_request, signing_config)
            signing_future.add_done_callback(lambda x: handshake_args.set_done(x.exception()))
        except Exception as e:
            handshake_args.set_done(e)

    return websockets_with_custom_handshake(_sign_websocket_handshake_request, websocket_proxy_options, **kwargs)


def websockets_with_custom_handshake(websocket_handshake_transform, websocket_proxy_options=None, **kwargs):
    _check_required_kwargs(**kwargs)
    tls_ctx_options = awscrt.io.TlsContextOptions()
    return _builder(tls_ctx_options=tls_ctx_options,
                    use_websockets=True,
                    websocket_handshake_transform=websocket_handshake_transform,
                    websocket_proxy_options=websocket_proxy_options,
                    **kwargs)
