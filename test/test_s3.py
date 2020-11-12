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

    def _S3ClientNew(self):

        event_loop_group = EventLoopGroup()
        host_resolver = DefaultHostResolver(event_loop_group)
        bootstrap = ClientBootstrap(event_loop_group, host_resolver)
        credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
        s3_client = S3Client(bootstrap, self.region, credential_provider)
        return s3_client

    def test_init_defaults(self):
        s3_client = self._S3ClientNew()
        # self.assertIsNotNone(s3_client)
        shutdown_event = s3_client.shutdown_event
        del s3_client
        print("what the fuck?")
        self.assertTrue(shutdown_event.wait(TIMEOUT))
        print("what?")
