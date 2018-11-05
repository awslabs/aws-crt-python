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
#include "io.h"
#include "mqtt.h"

#include <aws/io/io.h>
#include <aws/mqtt/mqtt.h>

void PyErr_SetAwsLastError(void) {
    PyErr_AwsLastError();
}

PyObject *PyErr_AwsLastError(void) {
    int err = aws_last_error();
    const char *msg = aws_error_str(err);
    return PyErr_Format(PyExc_RuntimeError, "%d: %s", err, msg);
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
    {"io_is_alpn_available", io_is_alpn_available, METH_NOARGS, NULL},
    {"io_new_event_loop_group", io_new_event_loop_group, METH_VARARGS, NULL},

    /* MQTT */
    {"mqtt_new_connection", mqtt_new_connection, METH_VARARGS, NULL},
    {"mqtt_set_will", mqtt_set_will, METH_VARARGS, NULL},
    {"mqtt_set_login", mqtt_set_login, METH_VARARGS, NULL},
    {"mqtt_publish", mqtt_publish, METH_VARARGS, NULL},
    {"mqtt_subscribe", mqtt_subscribe, METH_VARARGS, NULL},
    {"mqtt_unsubscribe", mqtt_unsubscribe, METH_VARARGS, NULL},
    {"mqtt_disconnect", mqtt_disconnect, METH_VARARGS, NULL},

    {NULL, NULL, 0, NULL},
};

static const char s_module_name[] = "_aws_crt_python";
PyDoc_STRVAR(s_module_doc, "C extension for binding AWS implementations of MQTT, HTTP, and friends");

/*******************************************************************************
 * Module Init
 ******************************************************************************/

#if PY_MAJOR_VERSION == 3
#    define INIT_FN PyInit__aws_crt_python
#elif PY_MAJOR_VERSION == 2
#    define INIT_FN init_aws_crt_python
#endif /* PY_MAJOR_VERSION */

PyMODINIT_FUNC INIT_FN(void) {

#if PY_MAJOR_VERSION == 3
    static struct PyModuleDef s_module_def = {
        PyModuleDef_HEAD_INIT,
        s_module_name,
        s_module_doc,
        -1, /* size of per-interpreter state of the module, or -1 if the module keeps state in global variables. */
        s_module_methods,
    };
    PyObject *m = PyModule_Create(&s_module_def);
#elif PY_MAJOR_VERSION == 2
    PyObject *m = Py_InitModule3(s_module_name, s_module_methods, s_module_doc);
    (void)m;
#endif /* PY_MAJOR_VERSION */

    aws_load_error_strings();
    aws_io_load_error_strings();
    aws_mqtt_load_error_strings();

#if PY_MAJOR_VERSION == 3
    return m;
#endif /* PY_MAJOR_VERSION */
}
