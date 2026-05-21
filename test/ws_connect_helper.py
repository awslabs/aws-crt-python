# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

# Helper for test_websocket subprocess scenarios.
# Runs awscrt.websocket.connect() against a host:port given on the command
# line and waits for on_connection_setup to fire. Used by tests that need
# to observe whether a malformed server response crashes the client process.

import sys
from concurrent.futures import Future

from awscrt.websocket import connect, create_handshake_request

TIMEOUT = 10.0


def main(host, port):
    setup_future = Future()
    connect(
        host=host,
        port=port,
        handshake_request=create_handshake_request(host=host),
        on_connection_setup=lambda x: setup_future.set_result(x))
    setup_future.result(TIMEOUT)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
