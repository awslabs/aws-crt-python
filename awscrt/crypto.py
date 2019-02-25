# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

class Hash(object):
    def __init__(self, native_handle):
        self._hash = native_handle

    @staticmethod
    def sha256_new():
        return Hash(native_handle=_aws_crt_python.aws_py_sha256_new())

    @staticmethod
    def md5_new():
        return Hash(native_handle=_aws_crt_python.aws_py_md5_new())

    def update(self, to_hash):
        _aws_crt_python.aws_py_hash_update(self._hash, to_hash)

    def digest(self, truncate_to = 0):
        tmp = _aws_crt_python.aws_py_hash_digest(self._hash, truncate_to)
        return tmp

class HMAC(object):
    def __init__(self, native_handle):
        self._hmac = native_handle

    @staticmethod
    def sha256_hmac_new(secret_key):
        return HMAC(native_handle=_aws_crt_python.aws_py_sha256_hmac_new(secret_key))

    def update(self, to_hmac):
        _aws_crt_python.aws_py_hmac_update(self._hmac, to_hmac)

    def digest(self, truncate_to = 0):
        return _aws_crt_python.aws_py_hmac_digest(self._hmac, truncate_to)
