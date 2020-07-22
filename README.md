## AWS CRT Python

Python bindings for the AWS Common Runtime.

API documentation: https://awslabs.github.io/aws-crt-python/

## License

This library is licensed under the Apache 2.0 License.

## OSX Only TLS Behavior

Please note that on OSX, once a private key is used with a certificate, that certificate-key pair is imported into the OSX Keychain.  All subsequent uses of that certificate will use the stored private key and ignore anything passed in programmatically.

## Installation

To install from pip:
````bash
python -m pip install awscrt
````

To install from Github:
````bash
git clone https://github.com/awslabs/aws-crt-python.git
cd aws-crt-python
git submodule update --init
python -m pip install .
````

To use from your Python application, declare `awscrt` as a dependency in your `setup.py` file.
