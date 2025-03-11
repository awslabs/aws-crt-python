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

To use from your Python application, declare `awscrt` as a dependency in your `setup.py` file.

### OpenSSL and LibCrypto (Unix only)

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

You can ignore all this on Windows and Apple platforms, where aws-crt-python
uses the OS's default libraries for TLS and cryptography math.

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

You can enable the crash handler by setting the environment variable `AWS_CRT_CRASH_HANDLER=1` . This will print the callstack to `stderr` in the event of a fatal error.

## Fork caveat

CRT is a multi-threading, is not safe to fork on the multi-thread process.
Fork is NOT supported with CRT resources running.
Fork and multiprocessing is not recommended to be use with CRT. Since CRT uses background threads, it can utilize the resources efficiently with on process.

But, as the CRT user and you **really** know what you are doing, there are some workarounds for some use case.

The major issue for fork is the forked process will only have the thread invokes the fork. All other threads will be gone from the child process.
To workaround this:
1. Release all CRT resources with background threads. Everything depends on `io.EventLoopGroup`, and the `io.EventLoopGroup` object itself, will needs to be released before fork
2. Wait for all threads to join before fork. `common.join_all_native_threads()` is a helper to track all the threads created by CRT will be joined from the main thread.

Specifically, refer to `test.test_s3.py.S3RequestTest.test_fork_workaround` for an example of the workaround.

More caveat: MacOS system libraries may start threads. You may see random crashes even if all CRT threads joined before fork on Mac. Try not using fork on MacOS, it's not a default for python since 3.8, [here](https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods).
