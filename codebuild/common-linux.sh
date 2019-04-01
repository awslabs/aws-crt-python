#!/bin/bash

set -e
set -x

CMAKE_ARGS="$@"

git submodule update --init --recursive
export AWS_C_INSTALL=`pwd`/build/deps/install

python3 setup.py build

# run tests
curl https://www.amazontrust.com/repository/AmazonRootCA1.pem --output /tmp/AmazonRootCA1.pem
cert=$(aws secretsmanager get-secret-value --secret-id "unit-test/certificate" --query "SecretString" | cut -f2 -d":" | cut -f2 -d\") && echo -e "$cert" > /tmp/certificate.pem
key=$(aws secretsmanager get-secret-value --secret-id "unit-test/privatekey" --query "SecretString" | cut -f2 -d":" | cut -f2 -d\") && echo -e "$key" > /tmp/privatekey.pem
ENDPOINT=$(aws secretsmanager get-secret-value --secret-id "unit-test/endpoint" --query "SecretString" | cut -f2 -d":" | sed -e 's/[\\\"\}]//g')

python3 test.py --endpoint $ENDPOINT --port 8883 --cert /tmp/certificate.pem --key /tmp/privatekey.pem --root-ca /tmp/AmazonRootCA1.pem
