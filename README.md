## AWS CRT Python

[![Version](https://img.shields.io/pypi/v/awscrt.svg?style=flat)](https://pypi.org/project/awscrt/)

Python 3 bindings for the AWS Common Runtime.

*   [API documentation](https://awslabs.github.io/aws-crt-python)
*   [Development guide](guides/dev/README.md) for contributors to aws-crt-python's source code.

## License

This library is licensed under the Apache 2.0 License.

## Minimum Requirements:
*   Python 3.7+

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

## OpenSSL and LibCrypto (Unix when install from Github only)

If your application uses OpenSSL, set environment variable 'AWS_CRT_BUILD_USE_SYSTEM_LIBCRYPTO' to 1 before install.

aws-crt-python does not use OpenSSL for TLS.
On Apple and Windows devices, the OS's default TLS library is used.
On Unix devices, [s2n-tls](https://github.com/aws/s2n-tls) is used.
But s2n-tls uses libcrypto, the cryptography math library bundled with OpenSSL.
To simplify the build process, the source code for s2n-tls and libcrypto are
included as git submodules and built along with aws-crt-python.
But if your application is also loading the system installation of OpenSSL
(i.e. your application uses libcurl which uses libssl which uses libcrypto)
there may be crashes as the application tries to use two different versions of libcrypto at once.

`export AWS_CRT_BUILD_USE_SYSTEM_LIBCRYPTO=1` will cause aws-crt-python to link against your system's existing `libcrypto`, instead of building its own copy.

You can ignore all this on Windows and Apple platforms, where aws-crt-python uses the OS's default libraries for TLS and cryptography math.
