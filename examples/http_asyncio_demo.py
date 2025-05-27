#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

"""
This example demonstrates how to use the asyncio HTTP client in awscrt.
It performs a simple GET request to httpbin.org and prints the response.
"""

import asyncio
import sys
from awscrt.io import ClientBootstrap, DefaultHostResolver, EventLoopGroup
from awscrt.http import HttpHeaders, HttpRequest
from awscrt.http_asyncio import HttpClientConnectionAsync


class Response:
    """Holds contents of incoming response"""

    def __init__(self):
        self.status_code = None
        self.headers = None
        self.body = bytearray()

    def on_response(self, http_stream, status_code, headers, **kwargs):
        print(f"Received response status: {status_code}")
        self.status_code = status_code
        self.headers = HttpHeaders(headers)
        for name, value in headers:
            print(f"Header: {name}: {value}")

    def on_body(self, http_stream, chunk, **kwargs):
        print(f"Received body chunk of size: {len(chunk)} bytes")
        self.body.extend(chunk)


async def make_request():
    """Perform an HTTP GET request asynchronously using the AWS CRT HTTP client."""
    # Create an event loop group and default host resolver
    event_loop_group = EventLoopGroup()
    host_resolver = DefaultHostResolver(event_loop_group)
    bootstrap = ClientBootstrap(event_loop_group, host_resolver)

    # Connect to httpbin.org
    host_name = "httpbin.org"
    port = 443

    print(f"Connecting to {host_name}:{port}...")
    connection = await HttpClientConnectionAsync.new(
        host_name=host_name,
        port=port,
        bootstrap=bootstrap,
        tls_connection_options=None  # For HTTPS, you would provide TLS options here
    )
    print("Connection established!")

    # Create and send a simple GET request
    print("Sending request...")
    request = HttpRequest("GET", "/get")
    request.headers.add("host", host_name)

    # Set up response handlers
    response = Response()
    print("before request")
    stream = connection.request(request, response.on_response, response.on_body)
    print("after request")
    stream.activate()
    print("activated")

    # Wait for the response to complete
    status_code = await stream.wait_for_completion()
    print(f"Request completed with status code: {status_code}")

    # Print the response body
    print("\nResponse body:")
    print(response.body.decode('utf-8'))

    # Close the connection
    print("Closing connection...")
    await connection.close()
    print("Connection closed!")


def main():
    """Entry point for the example."""
    try:
        asyncio.run(make_request())
        return 0
    except Exception as e:
        print(f"Exception: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
