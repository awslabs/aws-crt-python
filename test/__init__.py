# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt import NativeResource
from awscrt._test import check_for_leaks
from awscrt.http import HttpProxyOptions, HttpProxyAuthenticationType, HttpProxyConnectionType
from awscrt.io import init_logging, LogLevel, ClientTlsContext, TlsContextOptions
import os
import unittest
import sys

TIMEOUT = 10.0


class NativeResourceTest(unittest.TestCase):
    """
    Test fixture asserts there are no living NativeResources when a test completes.
    """

    _previous_test_failed = False

    def setUp(self):
        NativeResource._track_lifetime = True
        #init_logging(LogLevel.Trace, 'stderr')

    def tearDown(self):
        # Stop checking for leaks if any test has failed.
        # It's likely that the failed test leaks data, which will make
        # all future tests look like they're leaking too.
        if NativeResourceTest._previous_test_failed:
            return

        # Determine whether the current test just failed.
        # We check private members in unittest.TestCase to do this,
        # so the technique may stop working in some future python version.
        for outcome_err in self._outcome.errors:
            if outcome_err[1] is not None:
                NativeResourceTest._previous_test_failed = True
                return

        try:
            check_for_leaks(timeout_sec=TIMEOUT)
        except Exception:
            NativeResourceTest._previous_test_failed = True
            raise

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

    HTTP_PROXY_BASIC_USERNAME = os.environ.get('AWS_TEST_BASIC_AUTH_USERNAME')
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
            tls_ctx = ClientTlsContext(tls_ctx_opt)
            return tls_ctx.new_connection_options()
        else:
            return None

    @staticmethod
    def create_http_proxy_options_from_environment(test_type, auth_type):
        return HttpProxyOptions(ProxyTestConfiguration.get_proxy_host_for_test(test_type, auth_type),
                                ProxyTestConfiguration.get_proxy_port_for_test(test_type, auth_type),
                                tls_connection_options=ProxyTestConfiguration.get_proxy_tls_connection_options_for_test(test_type),
                                auth_type=auth_type,
                                auth_username=ProxyTestConfiguration.HTTP_PROXY_BASIC_USERNAME,
                                auth_password=ProxyTestConfiguration.HTTP_PROXY_BASIC_PASSWORD,
                                connection_type=ProxyTestConfiguration.get_proxy_connection_type_for_test(test_type))
