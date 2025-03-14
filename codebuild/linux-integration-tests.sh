#!/bin/bash

set -euxo pipefail

if test -f "/tmp/setup_proxy_test_env.sh"; then
    source /tmp/setup_proxy_test_env.sh
fi

env

git submodule update --init

# build package
cd $CODEBUILD_SRC_DIR

export AWS_TEST_S3=YES
python -m pip install --verbose ".[dev]"
python -m unittest discover --failfast --verbose 2>&1 | tee /tmp/tests.log
