## AWS CRT Python

[![Version](https://img.shields.io/pypi/v/awscrt.svg?style=flat)](https://pypi.org/project/awscrt/)

Python 3 bindings for the AWS Common Runtime.

*   [API documentation](https://awslabs.github.io/aws-crt-python)
*   [Development guide](guides/dev/README.md) for contributors to aws-crt-python's source code.

## License

This library is licensed under the Apache 2.0 License.

## Minimum Requirements:

*   Python 3.8+

## Installation

To install from pip:

```bash
python3 -m pip install awscrt
```

To install from Github:

```bash
git clone https://github.com/awslabs/aws-crt-python.git
cd aws-crt-python
git submodule update --init
python3 -m pip install .
```

To use from your Python application, declare `awscrt` as a dependency.

### OpenSSL and LibCrypto

aws-crt-python does not use OpenSSL for TLS.
On Apple and Windows devices, the OS's default TLS library is used.
On Unix devices, [s2n-tls](https://github.com/aws/s2n-tls) is used.
But s2n-tls uses libcrypto, the cryptography math library bundled with OpenSSL.

To simplify installation, aws-crt-python has its own copy of libcrypto.
This lets you install a wheel from PyPI without having OpenSSL installed.
Unix wheels on PyPI come with libcrypto statically compiled in.
Code to build libcrypto comes from [AWS-LC](https://github.com/aws/aws-lc).
AWS-LC's code is included in the PyPI source package,
and the git repository includes it as a submodule.

If you need aws-crt-python to use the libcrypto included on your system,
set environment variable `AWS_CRT_BUILD_USE_SYSTEM_LIBCRYPTO=1` while building from source:

```sh
AWS_CRT_BUILD_USE_SYSTEM_LIBCRYPTO=1 python3 -m pip install --no-binary :all: --verbose awscrt
```
( `--no-binary :all:` ensures you do not use the precompiled wheel from PyPI)

aws-crt-python also exposes a number of cryptographic primitives. 
On Unix, those depend on libcrypto as described above.
On Apple and Windows OS level crypto libraries are used whenever possible.
One exception to above statement is that for ED25519 keygen on Windows and Apple, 
libcrypto is used as no viable OS level alternative exists. In that case Unix level notes
about libcrypto apply to Apple and Windows as well. Libcrypto usage for ED25519 support is 
enabled on Windows and Apple by default and can be disabled by setting environment variable
`AWS_CRT_BUILD_DISABLE_LIBCRYPTO_USE_FOR_ED25519_EVERYWHERE` as follows:
(Note: ED25519 keygen functions will start returning not supported error in this case)
```sh
AWS_CRT_BUILD_DISABLE_LIBCRYPTO_USE_FOR_ED25519_EVERYWHERE=1 python3 -m pip install --no-binary :all: --verbose awscrt
```
( `--no-binary :all:` ensures you do not use the precompiled wheel from PyPI)

### AWS_CRT_BUILD_USE_SYSTEM_LIBS ###

aws-crt-python depends on several C libraries that make up the AWS Common Runtime (libaws-c-common, libaws-c-s3, etc).
By default, these libraries are built along with aws-crt-python and statically compiled in
(their source code is under [crt/](crt/)).

To skip building these dependencies, because they're already available on your system,
set environment variable `AWS_CRT_BUILD_USE_SYSTEM_LIBS=1` while building from source:

```sh
AWS_CRT_BUILD_USE_SYSTEM_LIBS=1 python3 -m pip install .
```

If these dependencies are available as both static and shared libs, you can force the static ones to be used by setting: `AWS_CRT_BUILD_FORCE_STATIC_LIBS=1`

## Mac-Only TLS Behavior

Please note that on Mac, once a private key is used with a certificate, that certificate-key pair is imported into the Mac Keychain. All subsequent uses of that certificate will use the stored private key and ignore anything passed in programmatically. Beginning in v0.6.2, when a stored private key from the Keychain is used, the following will be logged at the "info" log level:

```
static: certificate has an existing certificate-key pair that was previously imported into the Keychain. Using key from Keychain instead of the one provided.
```

## Crash Handler
You can enable the crash handler by setting the environment variable `AWS_CRT_CRASH_HANDLER=1`. This will print the callstack to `stderr` in the event of a fatal error.
