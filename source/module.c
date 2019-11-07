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

#include "auth.h"
#include "crypto.h"
#include "http.h"
#include "io.h"
#include "mqtt_client.h"
#include "mqtt_client_connection.h"

#include <aws/auth/auth.h>
#include <aws/common/byte_buf.h>
#include <aws/http/http.h>
#include <aws/io/io.h>
#include <aws/io/logging.h>
#include <aws/io/tls_channel_handler.h>
#include <aws/mqtt/mqtt.h>

#include <memoryobject.h>

static struct aws_logger s_logger;
static bool s_logger_init = false;

PyObject *aws_py_init_logging(PyObject *self, PyObject *args) {
    (void)self;

    if (s_logger_init) {
        Py_RETURN_NONE;
    }

    s_logger_init = true;

    struct aws_allocator *allocator = aws_py_get_allocator();

    int log_level = 0;
    const char *file_path = NULL;
    Py_ssize_t file_path_len = 0;

    if (!PyArg_ParseTuple(args, "bs#", &log_level, &file_path, &file_path_len)) {
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }

    struct aws_logger_standard_options log_options = {
        .level = log_level,
        .file = NULL,
        .filename = NULL,
    };

    Py_ssize_t stdout_len = (Py_ssize_t)strlen("stdout");

    Py_ssize_t cmp_len = file_path_len > stdout_len ? stdout_len : file_path_len;

    if (!memcmp("stdout", file_path, (size_t)cmp_len)) {
        log_options.file = stdout;
    } else if (!memcmp("stderr", file_path, (size_t)cmp_len)) {
        log_options.file = stderr;
    } else {
        log_options.filename = file_path;
    }

    aws_logger_init_standard(&s_logger, allocator, &log_options);
    aws_logger_set(&s_logger);

    Py_RETURN_NONE;
}

#if PY_MAJOR_VERSION == 3
#    define INIT_FN PyInit__awscrt
#    define UNICODE_GET_BYTES_FN PyUnicode_DATA
#    define UNICODE_GET_BYTE_LEN_FN PyUnicode_GET_LENGTH
#elif PY_MAJOR_VERSION == 2
#    define INIT_FN init_awscrt
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

PyObject *PyString_FromAwsString(const struct aws_string *aws_str) {
    return PyString_FromStringAndSize(aws_string_c_str(aws_str), aws_str->len);
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

int PyLongOrInt_Check(PyObject *obj) {
    if (PyLong_Check(obj)) {
        return 1;
    }
#if PY_MAJOR_VERSION == 2
    if (PyInt_Check(obj)) {
        return 1;
    }
#endif
    return 0;
}

void PyErr_SetAwsLastError(void) {
    PyErr_AwsLastError();
}

PyObject *PyErr_AwsLastError(void) {
    int err = aws_last_error();
    const char *name = aws_error_name(err);
    const char *msg = aws_error_str(err);
    return PyErr_Format(PyExc_RuntimeError, "%d (%s): %s", err, name, msg);
}

/* Key is `PyObject*` of Python exception type, value is `int` of AWS_ERROR_ enum (cast to void*) */
static struct aws_hash_table s_py_to_aws_error_map;

static void s_py_to_aws_error_map_init(void) {
    struct error_pair {
        PyObject *py_exception_type;
        int aws_error_code;
    };

    struct error_pair s_py_to_aws_error_array[] = {
        {PyExc_IndexError, AWS_ERROR_INVALID_INDEX},
        {PyExc_MemoryError, AWS_ERROR_OOM},
        {PyExc_NotImplementedError, AWS_ERROR_UNIMPLEMENTED},
        {PyExc_OverflowError, AWS_ERROR_OVERFLOW_DETECTED},
        {PyExc_TypeError, AWS_ERROR_INVALID_ARGUMENT},
        {PyExc_ValueError, AWS_ERROR_INVALID_ARGUMENT},
#if PY_MAJOR_VERSION == 3
        {PyExc_FileNotFoundError, AWS_ERROR_FILE_INVALID_PATH},
        {PyExc_BlockingIOError, AWS_IO_READ_WOULD_BLOCK},
        {PyExc_BrokenPipeError, AWS_IO_BROKEN_PIPE},
#endif
    };

    if (aws_hash_table_init(
            &s_py_to_aws_error_map,
            aws_py_get_allocator(),
            AWS_ARRAY_SIZE(s_py_to_aws_error_array),
            aws_hash_ptr,
            aws_ptr_eq,
            NULL /*destroy_key_fn*/,
            NULL /*destroy_value_fn*/)) {
        AWS_FATAL_ASSERT(0);
    }

    for (size_t i = 0; i < AWS_ARRAY_SIZE(s_py_to_aws_error_array); ++i) {
        const void *key = s_py_to_aws_error_array[i].py_exception_type;
        void *value = (void *)(size_t)s_py_to_aws_error_array[i].aws_error_code;
        if (aws_hash_table_put(&s_py_to_aws_error_map, key, value, NULL)) {
            AWS_FATAL_ASSERT(0);
        }
    }
}

int aws_py_raise_error(void) {
    AWS_ASSERT(PyErr_Occurred() != NULL);
    AWS_ASSERT(PyGILState_Check() == 1);

    int aws_error_code = AWS_ERROR_UNKNOWN;

    struct aws_hash_element *found;
    aws_hash_table_find(&s_py_to_aws_error_map, PyErr_Occurred(), &found);
    if (found) {
        aws_error_code = (int)(size_t)found->value;
    }

    /* Print standard traceback to sys.stderr and clear the error indicator. */
    PyErr_Print();
    fprintf(stderr, "Treating Python exception as error %d(%s)\n", aws_error_code, aws_error_name(aws_error_code));

    return aws_raise_error(aws_error_code);
}

PyObject *aws_py_memory_view_from_byte_buffer(struct aws_byte_buf *buf) {
    size_t available = buf->capacity - buf->len;
    if (available > PY_SSIZE_T_MAX) {
        PyErr_SetString(PyExc_OverflowError, "Buffer exceeds PY_SSIZE_T_MAX");
        return NULL;
    }

    Py_ssize_t mem_size = available;
    char *mem_start = (char *)(buf->buffer + buf->len);

#if PY_MAJOR_VERSION == 3
    return PyMemoryView_FromMemory(mem_start, mem_size, PyBUF_WRITE);
#else
    Py_buffer py_buf;
    int read_only = 0;
    if (PyBuffer_FillInfo(&py_buf, NULL /*obj*/, mem_start, mem_size, read_only, PyBUF_WRITABLE)) {
        return NULL;
    }

    return PyMemoryView_FromBuffer(&py_buf);
#endif /* PY_MAJOR_VERSION */
}

/*******************************************************************************
 * Allocator
 ******************************************************************************/

struct aws_allocator *aws_py_get_allocator(void) {
    return aws_default_allocator();
}

/*******************************************************************************
 * Definitions
 ******************************************************************************/

#define AWS_PY_METHOD_DEF(NAME, FLAGS)                                                                                 \
    { #NAME, aws_py_##NAME, (FLAGS), NULL }

static PyMethodDef s_module_methods[] = {
    /* IO */
    AWS_PY_METHOD_DEF(is_alpn_available, METH_NOARGS),
    AWS_PY_METHOD_DEF(event_loop_group_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(host_resolver_new_default, METH_VARARGS),
    AWS_PY_METHOD_DEF(client_bootstrap_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(client_tls_ctx_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(tls_connections_options_new_from_ctx, METH_VARARGS),
    AWS_PY_METHOD_DEF(tls_connection_options_set_alpn_list, METH_VARARGS),
    AWS_PY_METHOD_DEF(tls_connection_options_set_server_name, METH_VARARGS),
    AWS_PY_METHOD_DEF(init_logging, METH_VARARGS),

    /* MQTT Client */
    AWS_PY_METHOD_DEF(mqtt_client_new, METH_VARARGS),

    /* MQTT Client Connection */
    AWS_PY_METHOD_DEF(mqtt_client_connection_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(mqtt_client_connection_connect, METH_VARARGS),
    AWS_PY_METHOD_DEF(mqtt_client_connection_reconnect, METH_VARARGS),
    AWS_PY_METHOD_DEF(mqtt_client_connection_publish, METH_VARARGS),
    AWS_PY_METHOD_DEF(mqtt_client_connection_subscribe, METH_VARARGS),
    AWS_PY_METHOD_DEF(mqtt_client_connection_resubscribe_existing_topics, METH_VARARGS),
    AWS_PY_METHOD_DEF(mqtt_client_connection_unsubscribe, METH_VARARGS),
    AWS_PY_METHOD_DEF(mqtt_client_connection_disconnect, METH_VARARGS),

    /* Cryptographic primitives */
    AWS_PY_METHOD_DEF(md5_new, METH_NOARGS),
    AWS_PY_METHOD_DEF(sha256_new, METH_NOARGS),
    AWS_PY_METHOD_DEF(hash_update, METH_VARARGS),
    AWS_PY_METHOD_DEF(hash_digest, METH_VARARGS),
    AWS_PY_METHOD_DEF(sha256_hmac_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(hash_update, METH_VARARGS),
    AWS_PY_METHOD_DEF(hash_digest, METH_VARARGS),

    /* HTTP */
    AWS_PY_METHOD_DEF(http_connection_close, METH_VARARGS),
    AWS_PY_METHOD_DEF(http_connection_is_open, METH_VARARGS),
    AWS_PY_METHOD_DEF(http_client_connection_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(http_client_stream_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(http_request_new, METH_VARARGS),

    /* Auth */
    AWS_PY_METHOD_DEF(credentials_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(credentials_access_key_id, METH_VARARGS),
    AWS_PY_METHOD_DEF(credentials_secret_access_key, METH_VARARGS),
    AWS_PY_METHOD_DEF(credentials_session_token, METH_VARARGS),
    AWS_PY_METHOD_DEF(credentials_provider_get_credentials, METH_VARARGS),
    AWS_PY_METHOD_DEF(credentials_provider_shutdown, METH_VARARGS),
    AWS_PY_METHOD_DEF(credentials_provider_new_chain_default, METH_VARARGS),
    AWS_PY_METHOD_DEF(credentials_provider_new_static, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_new, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_algorithm, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_algorithm, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_credentials_provider, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_credentials_provider, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_region, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_region, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_service, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_service, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_date, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_date, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_should_sign_param, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_should_sign_param, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_use_double_uri_encode, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_use_double_uri_encode, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_should_normalize_uri_path, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_should_normalize_uri_path, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_get_sign_body, METH_VARARGS),
    AWS_PY_METHOD_DEF(signing_config_set_sign_body, METH_VARARGS),

    {NULL, NULL, 0, NULL},
};

static const char s_module_name[] = "_awscrt";
PyDoc_STRVAR(s_module_doc, "C extension for binding AWS implementations of MQTT, HTTP, and friends");

/*******************************************************************************
 * Module Init
 ******************************************************************************/

#if PY_MAJOR_VERSION == 3
static void s_module_free(void *userdata) {
    (void)userdata;

    aws_hash_table_clean_up(&s_py_to_aws_error_map);

    if (s_logger_init) {
        aws_logger_clean_up(&s_logger);
    }
    aws_mqtt_library_clean_up();
    aws_auth_library_clean_up();
    aws_http_library_clean_up();
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

    aws_http_library_init(aws_py_get_allocator());
    aws_auth_library_init(aws_py_get_allocator());
    aws_mqtt_library_init(aws_py_get_allocator());

    if (!PyEval_ThreadsInitialized()) {
        PyEval_InitThreads();
    }

    s_py_to_aws_error_map_init();

#if PY_MAJOR_VERSION == 3
    return m;
#endif /* PY_MAJOR_VERSION */
}
