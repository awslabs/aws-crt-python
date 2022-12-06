#!/bin/bash

set -euxo pipefail

env

git submodule update --init

# build package
cd $CODEBUILD_SRC_DIR

export AWS_TEST_S3=YES
python -m pip install --verbose .
python -m unittest --failfast --verbose 2>&1 | tee /tmp/tests.log test.test_mqtt5_canary
