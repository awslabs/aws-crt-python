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

## Fork and Multiprocessing

aws-crt-python uses background threads. This makes [os.fork()](https://docs.python.org/3/library/os.html#os.fork) unsafe. In a forked child process, all background threads vanish. The child will hang or crash when it tries to communicate with any of these (vanished) threads.

Unfortunately, Python's [multiprocessing](https://docs.python.org/3/library/multiprocessing.html) module defaults to using fork when it creates child processes (on POSIX systems except macOS, in Python versions 3.13 and earlier). `multiprocessing` is used under the hood by many tools that do work in parallel, including [concurrent.futures.ProcessPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor), and [pytorch.multiprocessing](https://pytorch.org/docs/stable/multiprocessing.html).

If you need to use `multiprocessing` with aws-crt-python, set it to use "spawn" or "forkserver" instead of "fork" ([see docs](https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods)). The Python community agrees, and `multiprocessing` will changes its default from "fork" to "spawn" in 3.14. It already uses "spawn" by default on macOS (because system libraries may start threads) and on Windows (because fork does not exist).

If you **must** use fork with aws-crt-python, you may be able to avoid hangs and crashes if you manage your threads very carefully:

1.	Release all CRT resources with background threads (e.g. clean up any `io.EventLoopGroup` instances).
2.	Join all CRT threads before forking (use `common.join_all_native_threads()` ).

For an example, see `test.test_s3.py.S3RequestTest.test_fork_workaround` .

## Mac-Only TLS Behavior

Please note that on Mac, once a private key is used with a certificate, that certificate-key pair is imported into the Mac Keychain. All subsequent uses of that certificate will use the stored private key and ignore anything passed in programmatically. Beginning in v0.6.2, when a stored private key from the Keychain is used, the following will be logged at the "info" log level:

```
static: certificate has an existing certificate-key pair that was previously imported into the Keychain. Using key from Keychain instead of the one provided.
```

## Crash Handler

You can enable the crash handler by setting the environment variable `AWS_CRT_CRASH_HANDLER=1` . This will print the callstack to `stderr` in the event of a fatal error.

## Advanced Build Options

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
