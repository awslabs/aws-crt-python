## AWS CRT Python

Python bindings for the AWS Common Runtime

## License

This library is licensed under the Apache 2.0 License.

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
