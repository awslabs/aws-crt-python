# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import _awscrt


class Hash(object):

    def __init__(self, native_handle):
        """
        don't call me, I'm private
        """
        self._hash = native_handle

    @staticmethod
    def sha256_new():
        """
        Creates a new instance of Hash, using the sha256 algorithm
        """
        return Hash(native_handle=_awscrt.sha256_new())

    @staticmethod
    def md5_new():
        """
        Creates a new instance of Hash, using the md5 algorithm.
        """
        return Hash(native_handle=_awscrt.md5_new())

    def update(self, to_hash):
        _awscrt.hash_update(self._hash, to_hash)

    def digest(self, truncate_to=0):
        return _awscrt.hash_digest(self._hash, truncate_to)


class HMAC(object):
    def __init__(self, native_handle):
        """
        don't call me, I'm private
        """
        self._hmac = native_handle

    @staticmethod
    def sha256_hmac_new(secret_key):
        """
        Creates a new instance of HMAC, using SHA256 HMAC as the algorithm and secret_key as the secret
        """
        return HMAC(native_handle=_awscrt.sha256_hmac_new(secret_key))

    def update(self, to_hmac):
        _awscrt.hmac_update(self._hmac, to_hmac)

    def digest(self, truncate_to=0):
        return _awscrt.hmac_digest(self._hmac, truncate_to)
