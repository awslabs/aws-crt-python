#!/bin/bash

set -e

CMAKE_ARGS="$@"

git submodule update --init --recursive
export AWS_C_INSTALL=`pwd`/build/deps/install

python3 setup.py install

# Tests cannot be run on ancient linux, which is detectable because it does not have lsb_release on it
LSB_BINARY=`which lsb_release`
if [ $LSB_BINARY == "" ]; then
    exit 0
fi

# run tests
curl https://www.amazontrust.com/repository/AmazonRootCA1.pem --output /tmp/AmazonRootCA1.pem
cert=$(aws secretsmanager get-secret-value --secret-id "unit-test/certificate" --query "SecretString" | cut -f2 -d":" | cut -f2 -d\") && echo -e "$cert" > /tmp/certificate.pem
key=$(aws secretsmanager get-secret-value --secret-id "unit-test/privatekey" --query "SecretString" | cut -f2 -d":" | cut -f2 -d\") && echo -e "$key" > /tmp/privatekey.pem
ENDPOINT=$(aws secretsmanager get-secret-value --secret-id "unit-test/endpoint" --query "SecretString" | cut -f2 -d":" | sed -e 's/[\\\"\}]//g')

echo --- unittest ---
python3 -m unittest discover

echo --- elasticurl GET ---
python3 elasticurl.py -v ERROR -i https://example.com

echo --- elasticurl PUT ---
python3 elasticurl.py -v ERROR -P -H "content-type: application/json" -i -d "{'test':'testval'}" http://httpbin.org/post

echo --- mqtt ---
python3 mqtt_test.py --endpoint $ENDPOINT --port 8883 --cert /tmp/certificate.pem --key /tmp/privatekey.pem --root-ca /tmp/AmazonRootCA1.pem

echo --- format check ---
# It would be great to do this earlier, but we want a pure pip environment for build/unittest.
# Tried doing earlier using venv but couldn't get it working in CI.
if python3 -m pip install autopep8; then
    python3 -m autopep8 --exit-code --diff --recursive awscrt test setup.py
fi
