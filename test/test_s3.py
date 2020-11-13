# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from awscrt.s3_client import S3Client
from test import NativeResourceTest, TIMEOUT
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from awscrt.auth import AwsCredentialsProvider
import io
import unittest


class S3ClientTest(NativeResourceTest):
    region = "us-west-2"
    timeout = 10  # seconds

    def _S3ClientNew(self, secure):

        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
        tls_option = None
        if secure:
            opt = TlsContextOptions()
            ctx = ClientTlsContext(opt)
            tls_option = TlsConnectionOptions(ctx)

        s3_client = S3Client(
            bootstrap=bootstrap,
            region=self.region,
            credential_provider=credential_provider,
            tls_connection_options=tls_option)

        return s3_client

    def test_sanity(self):
        s3_client = self._S3ClientNew(False)
        self.assertIsNotNone(s3_client)

    def test_sanity_secure(self):
        s3_client = self._S3ClientNew(True)
        self.assertIsNotNone(s3_client)

    def test_wait_shutdown(self):
        s3_client = self._S3ClientNew(False)
        self.assertIsNotNone(s3_client)
        shutdown_future = s3_client.shutdown_future
        del s3_client
        self.assertIsNone(shutdown_future.result(self.timeout))
