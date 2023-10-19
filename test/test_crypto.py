# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.


from test import NativeResourceTest
from awscrt.crypto import Hash, RSA, RSAEncryptionAlgorithm, RSASignatureAlgorithm
import unittest

RSA_PRIVATE_KEY_PEM = """
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAxaEsLWE2t3kJqsF1sFHYk7rSCGfGTSDa+3r5typT0cb/TtJ9
89C8dLcfInx4Dxq0ewo6NOxQ/TD8JevUda86jSh1UKEQUOl7qy+QwOhFMpwHq/uO
gMy5khDDLlkxD5U32RrDfqLK+4WUDapHlQ6g+E6wS1j1yDRoTZJk3WnTpR0sJHst
tLWV+mb2wPC7TkhGMbFMzbt6v0ahF7abVOOGiHVZ77uhS66hgP9nfgMHug8EN/xm
Vc/TxgMJci1Irh66xVZQ9aT2OZwb0TXglULm+b8HM+GKHgoTMwr9gAGpFDoYi22P
vxC/cqKHKIaYw7KNOPwImzQ6cp5oQJTAPQKRUwIDAQABAoIBACcuUfTZPiDX1UvO
OQfw4hA/zJ4v/MeTyPZspg9jS+TeIAW/g4sQChzVpU2QAbl04O031NxjMZdQ29yk
yaVfTStpJwEKPZLdB1CkCH3GTtm+x2KYZ+MvM2c6/Yc11Z0yRzU6siFsIvQEwpqG
9NQfZ1hzOU5m36uGgFtIt8iRz4z/RxpZUOXpaEosb0uMK3VPBuZBu8uVQBFdyAA7
xAGtJphxQ5u0Ct9aidPjD7MhCVzcb2XbgCgxb2hbCmDMOgeNVYrTo2fdBzNxLcXv
j4sUNmO+mLbUMFOePuP8JZaGNTTmznZkavskozfdbubuS3/4/0HH1goytFheVt1B
vfxzpgkCgYEA9QgEMKny0knDHV7BC2uAd7Vvd+5iikA3WdJ9i11zas9AbMMmf9cX
E3xNt6DO42hnVCNN4uAWH5uGWltWZ8pmGKk6mesqZfYPsyTz1cK6fP6KyQrkWRNT
V3nRMEMbziAWxFD5hxP9p1KlqI2Py+W4fJ0LGZ4Mwvn3dKYOilxK+50CgYEAznny
ZxQiJGt8/FtH9f/GDIY24Cz53Cuj+BWG2EH4kLo24ET2QTVvohFJVCm3Hf8Qe4cA
ASabRUg1vS4Tr2FmIqD2Iw/ogSmDcJdYuwhdtWKa8fDbehCN5hmXjn2WKYvjvZNv
Gcx6gfqULD9SaQv+N7lL8eJxKiLLBeVYD7qoha8CgYA8udnf/Z5yQ1mZw8vv+pqC
EHMps+iz/qo5FpOKoIRkKiz7R3oZIMNVTu8r3Syo600Aayd4XLTe7HplllFZs62N
2xLs5n1Be7P0X+oWRgZVx/e5T3u8H6/98/DGFzui4A0EZlURBwFMII1xsnO6wpnw
ODNyC9t5zt1nCWh9HdZveQKBgAm4+E8eRZVNcm83pSXSS3Mfhsn7lDBn5aqy6Mya
HqhB/H+G/8mGSKFrCvbpl/PTpOUMMFXdiYYzpkQoPUkO3w5WYgC4qQwb9lKA7e6w
sCjwYbduzgbrbKMfJWHSTBXcvnaY0Kx4UnR4Zi3HNYw4wlnBYfAb55RCWykF6aWj
9neFAoGBAMqQA2YWCHhnRtjn4iGMrTk8iOHBd8AGBBzX9rPKXDqWlOr/iQq90qX0
59309stR/bAhMzxOx31777XEPO1md854iXXr0XDMQlwCYkWyWb6hp4JlsqFBPMjn
nGXWA0Gp6UWgpg4Hvjdsu+0FQ3AhDMBKZZ8fBFb4EW+HRQIHPnbH
-----END RSA PRIVATE KEY-----
"""

RSA_PUBLIC_KEY_PEM = """
-----BEGIN RSA PUBLIC KEY-----
MIIBCgKCAQEAxaEsLWE2t3kJqsF1sFHYk7rSCGfGTSDa+3r5typT0cb/TtJ989C8
dLcfInx4Dxq0ewo6NOxQ/TD8JevUda86jSh1UKEQUOl7qy+QwOhFMpwHq/uOgMy5
khDDLlkxD5U32RrDfqLK+4WUDapHlQ6g+E6wS1j1yDRoTZJk3WnTpR0sJHsttLWV
+mb2wPC7TkhGMbFMzbt6v0ahF7abVOOGiHVZ77uhS66hgP9nfgMHug8EN/xmVc/T
xgMJci1Irh66xVZQ9aT2OZwb0TXglULm+b8HM+GKHgoTMwr9gAGpFDoYi22PvxC/
cqKHKIaYw7KNOPwImzQ6cp5oQJTAPQKRUwIDAQAB
-----END RSA PUBLIC KEY-----
"""


class TestCredentials(NativeResourceTest):

    def test_sha256_empty(self):
        h = Hash.sha256_new()
        digest = h.digest()
        expected = b'\xe3\xb0\xc4\x42\x98\xfc\x1c\x14\x9a\xfb\xf4\xc8\x99\x6f\xb9\x24\x27\xae\x41\xe4\x64\x9b\x93\x4c\xa4\x95\x99\x1b\x78\x52\xb8\x55'
        self.assertEqual(expected, digest)

    def test_sha256_one_shot(self):
        h = Hash.sha256_new()
        h.update('abc')
        digest = h.digest()
        expected = b'\xba\x78\x16\xbf\x8f\x01\xcf\xea\x41\x41\x40\xde\x5d\xae\x22\x23\xb0\x03\x61\xa3\x96\x17\x7a\x9c\xb4\x10\xff\x61\xf2\x00\x15\xad'
        self.assertEqual(expected, digest)

    def test_sha256_iterated(self):
        h = Hash.sha256_new()
        h.update('a')
        h.update('b')
        h.update('c')
        digest = h.digest()
        expected = b'\xba\x78\x16\xbf\x8f\x01\xcf\xea\x41\x41\x40\xde\x5d\xae\x22\x23\xb0\x03\x61\xa3\x96\x17\x7a\x9c\xb4\x10\xff\x61\xf2\x00\x15\xad'
        self.assertEqual(expected, digest)

    def test_sha1_empty(self):
        h = Hash.sha1_new()
        digest = h.digest()
        expected = b'\xda\x39\xa3\xee\x5e\x6b\x4b\x0d\x32\x55\xbf\xef\x95\x60\x18\x90\xaf\xd8\x07\x09'
        self.assertEqual(expected, digest)

    def test_sha1_one_shot(self):
        h = Hash.sha1_new()
        h.update('abc')
        digest = h.digest()
        expected = b'\xa9\x99\x3e\x36\x47\x06\x81\x6a\xba\x3e\x25\x71\x78\x50\xc2\x6c\x9c\xd0\xd8\x9d'
        self.assertEqual(expected, digest)

    def test_sha1_iterated(self):
        h = Hash.sha1_new()
        h.update('a')
        h.update('b')
        h.update('c')
        digest = h.digest()
        expected = b'\xa9\x99\x3e\x36\x47\x06\x81\x6a\xba\x3e\x25\x71\x78\x50\xc2\x6c\x9c\xd0\xd8\x9d'
        self.assertEqual(expected, digest)

    def test_md5_empty(self):
        h = Hash.md5_new()
        digest = h.digest()
        expected = b'\xd4\x1d\x8c\xd9\x8f\x00\xb2\x04\xe9\x80\x09\x98\xec\xf8\x42\x7e'
        self.assertEqual(expected, digest)

    def test_md5_one_shot(self):
        h = Hash.md5_new()
        h.update('abc')
        digest = h.digest()
        expected = b'\x90\x01\x50\x98\x3c\xd2\x4f\xb0\xd6\x96\x3f\x7d\x28\xe1\x7f\x72'
        self.assertEqual(expected, digest)

    def test_md5_iterated(self):
        h = Hash.md5_new()
        h.update('a')
        h.update('b')
        h.update('c')
        digest = h.digest()
        expected = b'\x90\x01\x50\x98\x3c\xd2\x4f\xb0\xd6\x96\x3f\x7d\x28\xe1\x7f\x72'
        self.assertEqual(expected, digest)

    def test_rsa_encryption_roundtrip(self):
        param_list = [RSAEncryptionAlgorithm.PKCS1_5,
                      RSAEncryptionAlgorithm.OAEP_SHA256,
                      RSAEncryptionAlgorithm.OAEP_SHA512]

        for p in param_list:
            with self.subTest(msg="RSA Encryption Roundtrip using algo p", p=p):
                test_pt = b'totally original test string'
                rsa = RSA.new_private_key_from_pem_data(RSA_PRIVATE_KEY_PEM)
                ct = rsa.encrypt(p, test_pt)
                pt = rsa.decrypt(p, ct)
                self.assertEqual(test_pt, pt)

                rsa_pub = RSA.new_public_key_from_pem_data(RSA_PUBLIC_KEY_PEM)
                ct_pub = rsa_pub.encrypt(p, test_pt)
                pt_pub = rsa.decrypt(p, ct_pub)
                self.assertEqual(test_pt, pt_pub)

    def test_rsa_signing_roundtrip(self):
        h = Hash.sha256_new()
        h.update(b'totally original test string')
        digest = h.digest()

        param_list = [RSASignatureAlgorithm.PKCS1_5_SHA256,
                      RSASignatureAlgorithm.PSS_SHA256]

        for p in param_list:
            with self.subTest(msg="RSA Signing Roundtrip using algo p", p=p):
                rsa = RSA.new_private_key_from_pem_data(RSA_PRIVATE_KEY_PEM)
                signature = rsa.sign(p, digest)
                self.assertTrue(rsa.verify(p, digest, signature))

                rsa_pub = RSA.new_private_key_from_pem_data(RSA_PRIVATE_KEY_PEM)
                self.assertTrue(rsa_pub.verify(p, digest, signature))

    def test_rsa_load_error(self):
        with self.assertRaises(ValueError):
            RSA.new_private_key_from_pem_data(RSA_PUBLIC_KEY_PEM)

        with self.assertRaises(ValueError):
            RSA.new_public_key_from_pem_data(RSA_PRIVATE_KEY_PEM)

    def test_rsa_signing_verify_fail(self):
        h = Hash.sha256_new()
        h.update(b'totally original test string')
        digest = h.digest()

        h2 = Hash.sha256_new()
        h2.update(b'another totally original test string')
        digest2 = h2.digest()

        rsa = RSA.new_private_key_from_pem_data(RSA_PRIVATE_KEY_PEM)
        signature = rsa.sign(RSASignatureAlgorithm.PKCS1_5_SHA256, digest)
        self.assertFalse(rsa.verify(RSASignatureAlgorithm.PKCS1_5_SHA256, digest2, signature))
        self.assertFalse(rsa.verify(RSASignatureAlgorithm.PKCS1_5_SHA256, digest, b'bad signature'))


if __name__ == '__main__':
    unittest.main()
