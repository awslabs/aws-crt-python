## AWS CRT Python

[![Version](https://img.shields.io/pypi/v/awscrt.svg?style=flat)](https://pypi.org/project/awscrt/)

Python 3 bindings for the AWS Common Runtime.

API documentation: https://awslabs.github.io/aws-crt-python/

## License

This library is licensed under the Apache 2.0 License.

## Minimum Requirements:
*   Python 3.6+

## Installation

To install from pip:
````bash
python3 -m pip install awscrt
````

To install from Github:
````bash
git clone https://github.com/awslabs/aws-crt-python.git
cd aws-crt-python
git submodule update --init
python3 -m pip install .
````

To use from your Python application, declare `awscrt` as a dependency in your `setup.py` file.

## Mac-Only TLS Behavior

Please note that on Mac, once a private key is used with a certificate, that certificate-key pair is imported into the Mac Keychain. All subsequent uses of that certificate will use the stored private key and ignore anything passed in programmatically. Beginning in v0.6.2, when a stored private key from the Keychain is used, the following will be logged at the "info" log level:

```
static: certificate has an existing certificate-key pair that was previously imported into the Keychain. Using key from Keychain instead of the one provided.
```

## Running tests

After install, run from project root:
```bash
python3 -m unittest discover --failfast --verbose
```

`--failfast` stops after one failed test.
This is useful because a failed test is likely to leak memory,
which will cause the rest of the tests to fail as well.

`--verbose` makes it easier to see which tests are skipped.

Many tests require an AWS account. These tests are skipped unless
specific environment variables are set:

MQTT
* AWS_TEST_IOT_MQTT_ENDPOINT - AWS account-specific endpoint to connect to IoT core by
* AWS_TEST_TLS_CERT_PATH - file path to certificate used to initialize the TLS context of the MQTT connection
* AWS_TEST_TLS_KEY_PATH - file path to the private key used to initialize the TLS context of the MQTT connection
* AWS_TEST_TLS_ROOT_CERT_PATH - file path to the root CA used to initialize the TLS context of the MQTT connection

PROXY
* AWS_TEST_HTTP_PROXY_HOST - host address of the proxy to use for tests that make open connections to the proxy
* AWS_TEST_HTTP_PROXY_PORT - port to use for tests that make open connections to the proxy
* AWS_TEST_HTTPS_PROXY_HOST - host address of the proxy to use for tests that make TLS-protected connections to the proxy
* AWS_TEST_HTTPS_PROXY_PORT - port to use for tests that make TLS-protected connections to the proxy
* AWS_TEST_HTTP_PROXY_BASIC_HOST - host address of the proxy to use for tests that make open connections to the proxy with basic authentication
* AWS_TEST_HTTP_PROXY_BASIC_PORT - port to use for tests that make open connections to the proxy with basic authentication
* AWS_TEST_BASIC_AUTH_USERNAME - username to use when using basic authentication to the proxy
* AWS_TEST_BASIC_AUTH_PASSWORD - password to use when using basic authentication to the proxy

S3
* AWS_TEST_S3 - set to any value to enable S3 tests
