## AWS CRT Python

Python 3 bindings for the AWS Common Runtime.

API documentation: https://awslabs.github.io/aws-crt-python/

## License

This library is licensed under the Apache 2.0 License.

## Minimum Requirements:
*   Python 3.5+

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
