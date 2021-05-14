# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from test import NativeResourceTest, TIMEOUT
from awscrt.http import HttpProxyOptions, HttpProxyAuthenticationType, HttpProxyConnectionType, HttpClientConnection, HttpClientStream, HttpRequest
from awscrt.io import init_logging, LogLevel, ClientTlsContext, TlsContextOptions, ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup
from awscrt.mqtt import Client, Connection
import os
import unittest
from test.test_http_client import Response
from test.test_mqtt import create_client_id


"""

# AWS_TEST_HTTP_PROXY_HOST - host address of the proxy to use for tests that make open connections to the proxy
# AWS_TEST_HTTP_PROXY_PORT - port to use for tests that make open connections to the proxy
# AWS_TEST_HTTPS_PROXY_HOST - host address of the proxy to use for tests that make tls-protected connections to the
    proxy
# AWS_TEST_HTTPS_PROXY_PORT - port to use for tests that make tls-protected connections to the proxy
# AWS_TEST_HTTP_PROXY_BASIC_HOST - host address of the proxy to use for tests that make open connections to the proxy
    with basic authentication
# AWS_TEST_HTTP_PROXY_BASIC_PORT - port to use for tests that make open connections to the proxy with basic
    authentication

# AWS_TEST_BASIC_AUTH_USERNAME - username to use when using basic authentication to the proxy
# AWS_TEST_BASIC_AUTH_PASSWORD - password to use when using basic authentication to the proxy

# AWS_TEST_TLS_CERT_PATH - file path to certificate used to initialize the tls context of the mqtt connection
# AWS_TEST_TLS_KEY_PATH - file path to the key used to initialize the tls context of the mqtt connection
# AWS_TEST_TLS_ROOT_CERT_PATH - file path to the root CA used to initialize the tls context of the mqtt connection

# AWS_TEST_IOT_SIGNING_REGION - AWS region to make a websocket connection to
# AWS_TEST_IOT_MQTT_ENDPOINT - AWS account-specific endpoint to connect to IoT core by

"""


class ProxyTestType:
    FORWARDING = 0
    TUNNELING_HTTP = 1
    TUNNELING_HTTPS = 2
    TUNNELING_DOUBLE_TLS = 3
    LEGACY_HTTP = 4
    LEGACY_HTTPS = 5


class ProxyTestConfiguration():
    HTTP_PROXY_HOST = os.environ.get('AWS_TEST_HTTP_PROXY_HOST')
    HTTP_PROXY_PORT = int(os.environ.get('AWS_TEST_HTTP_PROXY_PORT', '0'))
    HTTPS_PROXY_HOST = os.environ.get('AWS_TEST_HTTPS_PROXY_HOST')
    HTTPS_PROXY_PORT = int(os.environ.get('AWS_TEST_HTTPS_PROXY_PORT', '0'))
    HTTP_PROXY_BASIC_HOST = os.environ.get('AWS_TEST_HTTP_PROXY_BASIC_HOST')
    HTTP_PROXY_BASIC_PORT = int(os.environ.get('AWS_TEST_HTTP_PROXY_BASIC_PORT', '0'))

    HTTP_PROXY_BASIC_AUTH_USERNAME = os.environ.get('AWS_TEST_BASIC_AUTH_USERNAME')
    HTTP_PROXY_BASIC_AUTH_PASSWORD = os.environ.get('AWS_TEST_BASIC_AUTH_PASSWORD')

    HTTP_PROXY_TLS_CERT_PATH = os.environ.get('AWS_TEST_TLS_CERT_PATH')
    HTTP_PROXY_TLS_KEY_PATH = os.environ.get('AWS_TEST_TLS_KEY_PATH')
    HTTP_PROXY_TLS_ROOT_CA_PATH = os.environ.get('AWS_TEST_TLS_ROOT_CERT_PATH')

    HTTP_PROXY_WS_SIGNING_REGION = os.environ.get('AWS_TEST_IOT_SIGNING_REGION')
    HTTP_PROXY_MQTT_ENDPOINT = os.environ.get('AWS_TEST_IOT_MQTT_ENDPOINT')

    @staticmethod
    def is_proxy_environment_initialized():
        return ProxyTestConfiguration.HTTP_PROXY_HOST is not None and \
            ProxyTestConfiguration.HTTP_PROXY_PORT > 0 and \
            ProxyTestConfiguration.HTTPS_PROXY_HOST is not None and \
            ProxyTestConfiguration.HTTPS_PROXY_PORT > 0 and \
            ProxyTestConfiguration.HTTP_PROXY_BASIC_HOST is not None and \
            ProxyTestConfiguration.HTTP_PROXY_BASIC_PORT > 0 and \
            ProxyTestConfiguration.HTTP_PROXY_BASIC_AUTH_USERNAME is not None and \
            ProxyTestConfiguration.HTTP_PROXY_BASIC_AUTH_PASSWORD is not None

    @staticmethod
    def get_proxy_host_for_test(test_type, auth_type):
        if auth_type == HttpProxyAuthenticationType.Basic:
            return ProxyTestConfiguration.HTTP_PROXY_BASIC_HOST

        if test_type == ProxyTestType.TUNNELING_DOUBLE_TLS:
            return ProxyTestConfiguration.HTTPS_PROXY_HOST

        return ProxyTestConfiguration.HTTP_PROXY_HOST

    @staticmethod
    def get_proxy_port_for_test(test_type, auth_type):
        if auth_type == HttpProxyAuthenticationType.Basic:
            return ProxyTestConfiguration.HTTP_PROXY_BASIC_PORT

        if test_type == ProxyTestType.TUNNELING_DOUBLE_TLS:
            return ProxyTestConfiguration.HTTPS_PROXY_PORT

        return ProxyTestConfiguration.HTTP_PROXY_PORT

    @staticmethod
    def get_proxy_connection_type_for_test(test_type):
        if test_type == ProxyTestType.FORWARDING:
            return HttpProxyConnectionType.Forwarding
        elif test_type == ProxyTestType.TUNNELING_DOUBLE_TLS or \
                test_type == ProxyTestType.TUNNELING_HTTP or \
                test_type == ProxyTestType.TUNNELING_HTTPS:
            return HttpProxyConnectionType.Tunneling
        else:
            return HttpProxyConnectionType.Legacy

    @staticmethod
    def get_proxy_tls_connection_options_for_test(test_type):
        if test_type == ProxyTestType.TUNNELING_DOUBLE_TLS:
            tls_ctx_opt = TlsContextOptions()
            tls_ctx_opt.verify_peer = False
            tls_ctx = ClientTlsContext(tls_ctx_opt)
            tls_conn_opt = tls_ctx.new_connection_options()
            tls_conn_opt.set_server_name("localhost")
            return tls_conn_opt
        else:
            return None

    @staticmethod
    def create_http_proxy_options_from_environment(test_type, auth_type):
        return HttpProxyOptions(
            ProxyTestConfiguration.get_proxy_host_for_test(
                test_type,
                auth_type),
            ProxyTestConfiguration.get_proxy_port_for_test(
                test_type,
                auth_type),
            tls_connection_options=ProxyTestConfiguration.get_proxy_tls_connection_options_for_test(test_type),
            auth_type=auth_type,
            auth_username=ProxyTestConfiguration.HTTP_PROXY_BASIC_AUTH_USERNAME,
            auth_password=ProxyTestConfiguration.HTTP_PROXY_BASIC_AUTH_PASSWORD,
            connection_type=ProxyTestConfiguration.get_proxy_connection_type_for_test(test_type))

    @staticmethod
    def get_tls_connection_options_for_test(test_type, host_name):
        if test_type == ProxyTestType.FORWARDING or test_type == ProxyTestType.LEGACY_HTTP or test_type == ProxyTestType.TUNNELING_HTTP:
            return None
        else:
            tls_ctx_opt = TlsContextOptions()
            tls_ctx = ClientTlsContext(tls_ctx_opt)
            tls_conn_opt = tls_ctx.new_connection_options()
            tls_conn_opt.set_server_name(host_name)
            return tls_conn_opt

    @staticmethod
    def get_uri_from_test_type(test_type):
        if test_type == ProxyTestType.FORWARDING or test_type == ProxyTestType.LEGACY_HTTP or test_type == ProxyTestType.TUNNELING_HTTP:
            return "www.example.com"
        else:
            return "www.amazon.com"

    @staticmethod
    def get_port_from_test_type(test_type):
        if test_type == ProxyTestType.FORWARDING or test_type == ProxyTestType.LEGACY_HTTP or test_type == ProxyTestType.TUNNELING_HTTP:
            return 80
        else:
            return 443


class ProxyHttpTest(NativeResourceTest):

    def _establish_http_connection(self, test_type, uri, proxy_options):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        connection_future = HttpClientConnection.new(
            host_name=uri,
            port=ProxyTestConfiguration.get_port_from_test_type(test_type),
            bootstrap=bootstrap,
            tls_connection_options=ProxyTestConfiguration.get_tls_connection_options_for_test(
                test_type,
                uri),
            proxy_options=proxy_options)
        return connection_future.result(TIMEOUT)

    def _do_proxy_http_test(self, test_type, auth_type):
        uri = ProxyTestConfiguration.get_uri_from_test_type(test_type)
        proxy_options = ProxyTestConfiguration.create_http_proxy_options_from_environment(test_type, auth_type)
        connection = self._establish_http_connection(test_type, uri, proxy_options)

        request = HttpRequest('GET', '/')
        request.headers.add('host', uri)
        response = Response()
        stream = connection.request(request, response.on_response, response.on_body)
        stream.activate()

        # wait for stream to complete
        stream_completion_result = stream.completion_future.result(TIMEOUT)

        self.assertEqual(200, response.status_code)
        self.assertEqual(200, stream_completion_result)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_forwarding_proxy_no_auth(self):
        self._do_proxy_http_test(ProxyTestType.FORWARDING, HttpProxyAuthenticationType.Nothing)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_forwarding_proxy_legacy_http_no_auth(self):
        self._do_proxy_http_test(ProxyTestType.LEGACY_HTTP, HttpProxyAuthenticationType.Nothing)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_proxy_legacy_https_no_auth(self):
        self._do_proxy_http_test(ProxyTestType.LEGACY_HTTPS, HttpProxyAuthenticationType.Nothing)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_proxy_http_no_auth(self):
        self._do_proxy_http_test(ProxyTestType.TUNNELING_HTTP, HttpProxyAuthenticationType.Nothing)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_proxy_https_no_auth(self):
        self._do_proxy_http_test(ProxyTestType.TUNNELING_HTTPS, HttpProxyAuthenticationType.Nothing)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_proxy_double_tls_no_auth(self):
        self._do_proxy_http_test(ProxyTestType.TUNNELING_DOUBLE_TLS, HttpProxyAuthenticationType.Nothing)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_forwarding_proxy_basic_auth(self):
        self._do_proxy_http_test(ProxyTestType.FORWARDING, HttpProxyAuthenticationType.Basic)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_forwarding_proxy_legacy_http_basic_auth(self):
        self._do_proxy_http_test(ProxyTestType.LEGACY_HTTP, HttpProxyAuthenticationType.Basic)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_proxy_legacy_https_basic_auth(self):
        self._do_proxy_http_test(ProxyTestType.LEGACY_HTTPS, HttpProxyAuthenticationType.Basic)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_proxy_http_basic_auth(self):
        self._do_proxy_http_test(ProxyTestType.TUNNELING_HTTP, HttpProxyAuthenticationType.Basic)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_proxy_https_basic_auth(self):
        self._do_proxy_http_test(ProxyTestType.TUNNELING_HTTPS, HttpProxyAuthenticationType.Basic)

    def _establish_mqtt_connection(self, proxy_options):
        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        tls_opts = TlsContextOptions.create_client_with_mtls_from_path(
            ProxyTestConfiguration.HTTP_PROXY_TLS_CERT_PATH,
            ProxyTestConfiguration.HTTP_PROXY_TLS_KEY_PATH)
        tls_opts.override_default_trust_store_from_path(ca_filepath=ProxyTestConfiguration.HTTP_PROXY_TLS_ROOT_CA_PATH)
        tls = ClientTlsContext(tls_opts)

        client = Client(bootstrap, tls)
        connection = Connection(
            client=client,
            client_id=create_client_id(),
            host_name=ProxyTestConfiguration.HTTP_PROXY_MQTT_ENDPOINT,
            port=8883,
            proxy_options=proxy_options)
        connection.connect().result(TIMEOUT)
        return connection

    def _do_proxy_mqtt_test(self, test_type, auth_type):
        proxy_options = ProxyTestConfiguration.create_http_proxy_options_from_environment(test_type, auth_type)
        connection = self._establish_mqtt_connection(proxy_options)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_http_proxy_mqtt_no_auth(self):
        self._do_proxy_mqtt_test(ProxyTestType.TUNNELING_HTTP, HttpProxyAuthenticationType.Nothing)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_http_proxy_mqtt_basic_auth(self):
        self._do_proxy_mqtt_test(ProxyTestType.TUNNELING_HTTP, HttpProxyAuthenticationType.Basic)

    @unittest.skipIf(not ProxyTestConfiguration.is_proxy_environment_initialized(), 'requires proxy test env vars')
    def test_tunneling_http_proxy_mqtt_double_tls(self):
        self._do_proxy_mqtt_test(ProxyTestType.TUNNELING_DOUBLE_TLS, HttpProxyAuthenticationType.Nothing)


if __name__ == '__main__':
    unittest.main()
