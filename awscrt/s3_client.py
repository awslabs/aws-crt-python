"""
S3 client
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt
from concurrent.futures import Future
from awscrt import NativeResource
from awscrt.io import ClientBootstrap, EventLoopGroup, DefaultHostResolver, TlsConnectionOptions
from awscrt.auth import AwsCredentialsProvider


class S3Client(NativeResource):
    """S3 client

    Args:
        bootstrap (ClientBootstrap): Client bootstrap to use when initiating socket connection.

        region (str): Region that the S3 bucket lives in.

        credential_provider (Optional[AwsCredentialsProvider]): Credentials providers source the
            AwsCredentials needed to sign an authenticated AWS request.
            If None is provided, then the default chain credential provider will be used

        tls_connection_options (Optional[TlsConnectionOptions]): Optional TLS
            connection options. If None is provided, then the connection will
            be attempted over plain-text.

        part_size (Optional[int]): Size of parts the files will be downloaded or uploaded in.

        connection_timeout_ms (Optional[int]): Timeout value, in milliseconds, used for each connection.

        throughput_target_gbps (Optional[float]): Throughput target in Gbps that we are trying to reach.

        throughput_per_vip_gbps (Optional[float]): Amount of throughput in Gbps to designate to each VIP.

        num_connections_per_vip (Optional[int]): The number of connections that each VIP will have.
    """

    __slots__ = ('_shutdown_future')

    def __init__(
            self,
            bootstrap,
            region,
            credential_provider=None,
            tls_connection_options=None,
            part_size=0,
            connection_timeout_ms=0,
            throughput_target_gbps=0,
            throughput_per_vip_gbps=0,
            num_connections_per_vip=0):
        assert isinstance(bootstrap, ClientBootstrap) or bootstrap is None
        assert isinstance(region, str)
        assert isinstance(credential_provider, AwsCredentialsProvider) or credential_provider is None
        assert isinstance(tls_connection_options, TlsConnectionOptions) or tls_connection_options is None
        assert isinstance(part_size, int) or part_size is None
        assert isinstance(connection_timeout_ms, int) or connection_timeout_ms is None
        assert isinstance(
            throughput_target_gbps,
            int) or isinstance(
            throughput_target_gbps,
            float) or throughput_target_gbps is None
        assert isinstance(
            throughput_per_vip_gbps,
            int) or isinstance(
            throughput_per_vip_gbps,
            float) or throughput_per_vip_gbps is None
        assert isinstance(num_connections_per_vip, int) or num_connections_per_vip is None

        if not bootstrap:
            event_loop_group = EventLoopGroup(1)
            host_resolver = DefaultHostResolver(event_loop_group)
            bootstrap = ClientBootstrap(event_loop_group, host_resolver)

        if not credential_provider:
            credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)

        super().__init__()

        self._shutdown_future = Future()

        def on_shutdown():
            self._shutdown_future.set_result(None)

        self._binding = _awscrt.s3_client_new(
            bootstrap,
            credential_provider,
            tls_connection_options,
            on_shutdown,
            region,
            part_size,
            connection_timeout_ms,
            throughput_target_gbps,
            throughput_per_vip_gbps,
            num_connections_per_vip)

    @property
    def shutdown_future(self):
        """
        concurrent.futures.Future: Completes when this client has finished shutting down.
        Future will contain nothing.
        Note that the connection may have been garbage-collected before this future completes.
        """
        return self._shutdown_future
