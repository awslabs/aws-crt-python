/*
 * Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
#include "crypto.h"
#include "http_client_connection.h"
#include "io.h"
#include "mqtt_client.h"
#include "mqtt_client_connection.h"

#include <aws/common/byte_buf.h>
#include <aws/io/io.h>
#include <aws/io/logging.h>
#include <aws/io/tls_channel_handler.h>

#include <aws/http/http.h>
#include <aws/mqtt/mqtt.h>

#include <memoryobject.h>

#if PY_MAJOR_VERSION == 3
#    define INIT_FN PyInit__aws_crt_python
#    define UNICODE_GET_BYTES_FN PyUnicode_DATA
#    define UNICODE_GET_BYTE_LEN_FN PyUnicode_GET_LENGTH
#elif PY_MAJOR_VERSION == 2
#    define INIT_FN init_aws_crt_python
#    define UNICODE_GET_BYTES_FN PyUnicode_AS_DATA
#    define UNICODE_GET_BYTE_LEN_FN PyUnicode_GET_DATA_SIZE
#endif /* PY_MAJOR_VERSION */

struct aws_byte_cursor aws_byte_cursor_from_pystring(PyObject *str) {
    if (PyBytes_CheckExact(str)) {
        return aws_byte_cursor_from_array(PyBytes_AsString(str), PyBytes_Size(str));
    }
    if (PyUnicode_CheckExact(str)) {
        return aws_byte_cursor_from_array(UNICODE_GET_BYTES_FN(str), UNICODE_GET_BYTE_LEN_FN(str));
    }

    return aws_byte_cursor_from_array(NULL, 0);
}

int PyIntEnum_Check(PyObject *int_enum_obj) {
#if PY_MAJOR_VERSION == 2
    return PyInt_Check(int_enum_obj);
#else
    return PyLong_Check(int_enum_obj);
#endif
}

long PyIntEnum_AsLong(PyObject *int_enum_obj) {
#if PY_MAJOR_VERSION == 2
    return PyInt_AsLong(int_enum_obj);
#else
    return PyLong_AsLong(int_enum_obj);
#endif
}

void PyErr_SetAwsLastError(void) {
    PyErr_AwsLastError();
}

PyObject *PyErr_AwsLastError(void) {
    int err = aws_last_error();
    const char *msg = aws_error_str(err);
    return PyErr_Format(PyExc_RuntimeError, "%d: %s", err, msg);
}

PyObject *aws_py_memory_view_from_byte_buffer(struct aws_byte_buf *buf, int flags) {
#if PY_MAJOR_VERSION == 3
    return PyMemoryView_FromMemory((char *)(buf->buffer + buf->len), (Py_size_t)(buf->capacity - buf->len), flags);
#else
    Py_buffer py_buf;
    Py_ssize_t size = buf->capacity - buf->len;

    int read_only = (flags & PyBUF_WRITE) != PyBUF_WRITE;
    if (PyBuffer_FillInfo(&py_buf, NULL, (char *)(buf->buffer + buf->len), size, read_only, PyBUF_CONTIG)) {
        return NULL;
    }

    return PyMemoryView_FromBuffer(&py_buf);
#endif /* PY_MAJOR_VERSION */
}

/*******************************************************************************
 * Allocator
 ******************************************************************************/

struct aws_allocator *aws_crt_python_get_allocator(void) {
    return aws_default_allocator();
}

/*******************************************************************************
 * Definitions
 ******************************************************************************/

static PyMethodDef s_module_methods[] = {
    /* IO */
    {"aws_py_is_alpn_available", aws_py_is_alpn_available, METH_NOARGS, NULL},
    {"aws_py_io_event_loop_group_new", aws_py_io_event_loop_group_new, METH_VARARGS, NULL},
    {"aws_py_io_host_resolver_new_default", aws_py_io_host_resolver_new_default, METH_VARARGS, NULL},
    {"aws_py_io_client_bootstrap_new", aws_py_io_client_bootstrap_new, METH_VARARGS, NULL},
    {"aws_py_io_client_tls_ctx_new", aws_py_io_client_tls_ctx_new, METH_VARARGS, NULL},
    {"aws_py_io_tls_connections_options_new_from_ctx",
     aws_py_io_tls_connections_options_new_from_ctx,
     METH_VARARGS,
     NULL},
    {"aws_py_io_tls_connection_options_set_alpn_list",
     aws_py_io_tls_connection_options_set_alpn_list,
     METH_VARARGS,
     NULL},
    {"aws_py_io_tls_connection_options_set_server_name",
     aws_py_io_tls_connection_options_set_server_name,
     METH_VARARGS,
     NULL},
    {"aws_py_io_init_logging", aws_py_io_init_logging, METH_VARARGS, NULL},

    /* MQTT Client */
    {"aws_py_mqtt_client_new", aws_py_mqtt_client_new, METH_VARARGS, NULL},

    /* MQTT Client Connection */
    {"aws_py_mqtt_client_connection_new", aws_py_mqtt_client_connection_new, METH_VARARGS, NULL},
    {"aws_py_mqtt_client_connection_connect", aws_py_mqtt_client_connection_connect, METH_VARARGS, NULL},
    {"aws_py_mqtt_client_connection_reconnect", aws_py_mqtt_client_connection_reconnect, METH_VARARGS, NULL},
    {"aws_py_mqtt_client_connection_publish", aws_py_mqtt_client_connection_publish, METH_VARARGS, NULL},
    {"aws_py_mqtt_client_connection_subscribe", aws_py_mqtt_client_connection_subscribe, METH_VARARGS, NULL},
    {"aws_py_mqtt_client_connection_unsubscribe", aws_py_mqtt_client_connection_unsubscribe, METH_VARARGS, NULL},
    {"aws_py_mqtt_client_connection_ping", aws_py_mqtt_client_connection_ping, METH_VARARGS, NULL},
    {"aws_py_mqtt_client_connection_disconnect", aws_py_mqtt_client_connection_disconnect, METH_VARARGS, NULL},

    /* Cryptographic primitives */
    {"aws_py_md5_new", aws_py_md5_new, METH_NOARGS, NULL},
    {"aws_py_sha256_new", aws_py_sha256_new, METH_NOARGS, NULL},
    {"aws_py_hash_update", aws_py_hash_update, METH_VARARGS, NULL},
    {"aws_py_hash_digest", aws_py_hash_digest, METH_VARARGS, NULL},
    {"aws_py_sha256_hmac_new", aws_py_sha256_hmac_new, METH_VARARGS, NULL},
    {"aws_py_hmac_update", aws_py_hash_update, METH_VARARGS, NULL},
    {"aws_py_hmac_digest", aws_py_hash_digest, METH_VARARGS, NULL},

    /* HTTP client */
    {"aws_py_http_client_connection_create", aws_py_http_client_connection_create, METH_VARARGS, NULL},
    {"aws_py_http_client_connection_close", aws_py_http_client_connection_close, METH_VARARGS, NULL},
    {"aws_py_http_client_connection_is_open", aws_py_http_client_connection_is_open, METH_VARARGS, NULL},
    {"aws_py_http_client_connection_make_request", aws_py_http_client_connection_make_request, METH_VARARGS, NULL},

    {NULL, NULL, 0, NULL},
};

static const char s_module_name[] = "_aws_crt_python";
PyDoc_STRVAR(s_module_doc, "C extension for binding AWS implementations of MQTT, HTTP, and friends");

/*******************************************************************************
 * Module Init
 ******************************************************************************/

#if PY_MAJOR_VERSION == 3
static void s_module_free(void *userdata) {
    (void)userdata;

    aws_tls_clean_up_static_state();
}
#endif /* PY_MAJOR_VERSION == 3 */

PyMODINIT_FUNC INIT_FN(void) {

#if PY_MAJOR_VERSION == 3
    static struct PyModuleDef s_module_def = {
        PyModuleDef_HEAD_INIT,
        s_module_name,
        s_module_doc,
        -1, /* size of per-interpreter state of the module, or -1 if the module keeps state in global variables. */
        s_module_methods,
        NULL,
        NULL,
        NULL,
        s_module_free,
    };
    PyObject *m = PyModule_Create(&s_module_def);
#elif PY_MAJOR_VERSION == 2
    PyObject *m = Py_InitModule3(s_module_name, s_module_methods, s_module_doc);
    (void)m;
#endif /* PY_MAJOR_VERSION */

    aws_load_error_strings();
    aws_io_load_error_strings();
    aws_mqtt_load_error_strings();

    aws_io_load_log_subject_strings();
    aws_http_library_init(aws_crt_python_get_allocator());

    aws_tls_init_static_state(aws_crt_python_get_allocator());
    if (!PyEval_ThreadsInitialized()) {
        PyEval_InitThreads();
    }
#if PY_MAJOR_VERSION == 3
    return m;
#endif /* PY_MAJOR_VERSION */
}
