#ifndef AWS_CRT_PYTHON_MQTT_CLIENT_H
#define AWS_CRT_PYTHON_MQTT_CLIENT_H
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

#include <aws/mqtt/client.h>

/** Name string for client capsules. */
extern const char *s_capsule_name_mqtt_client;

struct mqtt_python_client {
    struct aws_mqtt_client native_client;
};

PyObject *mqtt_client_new(PyObject *self, PyObject *args);

#endif /* AWS_CRT_PYTHON_MQTT_CLIENT_H */
