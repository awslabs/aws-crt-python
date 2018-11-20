# Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

import _aws_crt_python

def is_alpn_available():
    return _aws_crt_python.aws_py_is_alpn_available()

class EventLoopGroup(object):
    __slots__ = ['_internal_elg']

    def __init__(self, num_threads):
        self._internal_elg = _aws_crt_python.aws_py_io_event_loop_group_new(num_threads)

class ClientBootstrap(object):
    __slots__ = ['elg', '_internal_bootstrap']

    def __init__(self, elg):
        assert isinstance(elg, EventLoopGroup)

        self.elg = elg
        self._internal_bootstrap = _aws_crt_python.aws_py_io_client_bootstrap_new(self.elg._internal_elg)
