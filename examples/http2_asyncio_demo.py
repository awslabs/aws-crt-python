#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

"""
This example demonstrates how to use the asyncio HTTP/2 client in awscrt.
It performs multiple concurrent requests to httpbin.org and shows HTTP/2 features.
"""

import asyncio
import sys
import io
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions
from awscrt.http import HttpHeaders, HttpRequest, Http2Setting, Http2SettingID
from awscrt.http_asyncio import Http2ClientConnectionAsync
from awscrt_python_logging_example import PythonLoggingRedirector
import awscrt.io
import logging


class Response:
    """Holds contents of incoming response"""

    def __init__(self, request_name):
        self.request_name = request_name
        self.status_code = None
        self.headers = None
        self.body = bytearray()

    def on_response(self, http_stream, status_code, headers, **kwargs):
        print(f"[{self.request_name}] Received response status: {status_code}")
        self.status_code = status_code
        self.headers = HttpHeaders(headers)
        for name, value in headers:
            print(f"[{self.request_name}] Header: {name}: {value}")

    def on_body(self, http_stream, chunk, **kwargs):
        print(f"[{self.request_name}] Received body chunk of size: {len(chunk)} bytes")
        self.body.extend(chunk)


# Create an event for synchronizing remote settings
remote_settings_event = None
event_loop = None


def on_remote_settings_changed(settings):
    """Handler for when the server updates HTTP/2 settings"""
    print("Remote HTTP/2 settings changed:")
    for setting in settings:
        print(f"  - {setting.id.name} = {setting.value}")
    # Signal that remote settings have been received
    # This callback is called from a different thread, so we need to use call_soon_threadsafe
    if event_loop and remote_settings_event:
        event_loop.call_soon_threadsafe(remote_settings_event.set)


async def make_concurrent_requests():
    """Perform multiple concurrent HTTP/2 requests asynchronously."""
    global remote_settings_event, event_loop

    # Get the current event loop and create the event
    event_loop = asyncio.get_running_loop()
    remote_settings_event = asyncio.Event()

    # Create an event loop group and default host resolver
    event_loop_group = EventLoopGroup()
    host_resolver = DefaultHostResolver(event_loop_group)
    bootstrap = ClientBootstrap(event_loop_group, host_resolver)

    # Connect to httpbin.org
    host_name = "localhost"  # Change to "httpbin.org" for real requests
    port = 3443

    # TLS options for HTTP/2
    tls_ctx_opt = TlsContextOptions()
    tls_ctx_opt.verify_peer = False
    tls_ctx = ClientTlsContext(tls_ctx_opt)
    tls_conn_opt = tls_ctx.new_connection_options()
    tls_conn_opt.set_server_name(host_name)
    tls_conn_opt.set_alpn_list(["h2"])  # Set ALPN to HTTP/2

    # Initial HTTP/2 settings
    initial_settings = [
        Http2Setting(Http2SettingID.ENABLE_PUSH, 0),
        Http2Setting(Http2SettingID.MAX_CONCURRENT_STREAMS, 100),
        Http2Setting(Http2SettingID.INITIAL_WINDOW_SIZE, 65535),
    ]

    print(f"Connecting to {host_name}:{port} using HTTP/2...")
    connection = await Http2ClientConnectionAsync.new(
        host_name=host_name,
        port=port,
        bootstrap=bootstrap,
        tls_connection_options=tls_conn_opt,
        initial_settings=initial_settings,
        on_remote_settings_changed=on_remote_settings_changed
    )
    print("HTTP/2 Connection established!")

    # Wait for remote settings to be received
    print("Waiting for remote settings...")
    await remote_settings_event.wait()
    print("Remote settings received, proceeding with requests...")

    try:
        # Create several requests to be executed concurrently
        tasks = []

        # # Request 1: Simple GET
        # tasks.append(send_get_request(connection, host_name))

        # # Request 2: POST with JSON body
        # tasks.append(send_post_request(connection, host_name))

        # Request 3: Stream data using manual write mode
        tasks.append(send_stream_request(connection, host_name))

        # Wait for all requests to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Task {i} failed with exception: {result}")

    finally:
        # Add a small delay to ensure all responses are received
        await asyncio.sleep(1)

        # Close the connection
        print("Closing connection...")
        await connection.close()
        print("Connection closed!")


async def send_get_request(connection, host_name):
    """Send a GET request using the HTTP/2 connection."""
    print("Sending GET request...")
    request = HttpRequest("GET", "/get?param1=value1&param2=value2")
    request.headers.add("host", host_name)

    # Set up response handler
    response = Response("GET")
    stream = connection.request(request, response.on_response, response.on_body)
    stream.activate()

    # Wait for completion
    status_code = await stream.wait_for_completion()
    print(f"GET request completed with status code: {status_code}")
    print("\nGET Response body:")
    print(response.body.decode("utf-8"))
    return status_code


async def send_post_request(connection, host_name):
    """Send a POST request with JSON body using the HTTP/2 connection."""
    print("Sending POST request with JSON body...")

    # Prepare JSON payload
    json_payload = '{"name": "Example User", "id": 12345}'

    # Create request with headers
    request = HttpRequest("POST", "/post")
    request.headers.add("host", host_name)
    request.headers.add("content-type", "application/json")
    request.headers.add("content-length", str(len(json_payload)))

    # Set the body using BytesIO stream
    request.body_stream = io.BytesIO(json_payload.encode("utf-8"))

    # Set up response handler
    response = Response("POST")
    stream = connection.request(request, response.on_response, response.on_body)
    stream.activate()

    # Wait for completion
    status_code = await stream.wait_for_completion()
    print(f"POST request completed with status code: {status_code}")
    print("\nPOST Response body:")
    print(response.body.decode("utf-8"))
    return status_code


async def send_stream_request(connection, host_name):
    """Send a request with streamed data using manual write mode."""
    print("Sending request with manual data streaming...")

    # Create request
    request = HttpRequest("PUT", "/put")
    request.headers.add("host", host_name)
    request.headers.add("content-type", "text/plain")
    # Note: We don't set content-length as we're streaming the data

    # Set up response handler
    response = Response("STREAM")
    stream = connection.request(request, response.on_response, response.on_body, manual_write=True)
    stream.activate()

    # Stream data in chunks
    data_chunks = [
        b"This is the first chunk of data.\n",
        b"This is the second chunk of data.\n",
        b"This is the final chunk of data."
    ]

    # for i, chunk in enumerate(data_chunks):
    #     print(f"Sending chunk {i + 1}/{len(data_chunks)}, size: {len(chunk)} bytes")
    #     # Use BytesIO for each chunk
    #     chunk_stream = io.BytesIO(chunk)
    #     await stream.write_data(chunk_stream, end_stream=(i == len(data_chunks) - 1))
    #     # Simulate processing time between chunks
    #     await asyncio.sleep(0.1)
    await stream.write_data(io.BytesIO(data_chunks[0]), end_stream=False)
    await stream.write_data(io.BytesIO(data_chunks[1]), end_stream=True)
    # await stream.write_data(io.BytesIO(data_chunks[1]), end_stream=True)
    result = await stream.next()

    # Wait for completion
    status_code = await stream.wait_for_completion()
    print(f"Stream request completed with status code: {status_code}")
    print("\nStream Response body:", result)
    print(response.body.decode("utf-8"))
    return status_code


def main():
    """Entry point for the example."""
    try:

        # Set up Python logging
        logging.basicConfig(level=logging.DEBUG)

        # Create and activate redirector
        # redirector = PythonLoggingRedirector(base_logger_name="myapp.awscrt")
        # redirector.activate(aws_log_level=awscrt.io.LogLevel.Trace)

        asyncio.run(make_concurrent_requests())
        # Your AWS CRT operations here...
        # Logs will now appear in Python's logging system

        # redirector.deactivate()
        return 0
    except Exception as e:
        print(f"Exception: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
