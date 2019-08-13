#ifndef AWS_CRT_PYTHON_HTTP_STREAM_H
#define AWS_CRT_PYTHON_HTTP_STREAM_H
/*
 * Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *  http://aws.amazon.com/apache2.0
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

#include "module.h"
#include "http_connection.h"
#include <aws/http/connection.h>
#include <aws/http/request_response.h>
#include <aws/io/stream.h>

extern const char *s_capsule_name_http_stream;

struct py_http_stream {
    struct aws_allocator *allocator;
    struct aws_http_stream *stream;
    struct aws_input_stream body_input_stream;
    PyObject *capsule;
    PyObject *on_stream_completed;
    PyObject *on_incoming_headers_received;
    PyObject *outgoing_body;
    PyObject *on_incoming_body;
    PyObject *received_headers;
    bool is_eos;
    /* only for server side */
    PyObject *on_request_done;
};

void native_http_stream_destructor(PyObject *http_stream_capsule);

int native_on_incoming_headers(
    struct aws_http_stream *internal_stream,
    const struct aws_http_header *header_array,
    size_t num_headers,
    void *user_data);

int native_on_incoming_body(
    struct aws_http_stream *internal_stream,
    const struct aws_byte_cursor *data,
    void *user_data);

void native_on_stream_complete(struct aws_http_stream *internal_stream, int error_code, void *user_data);

#endif
