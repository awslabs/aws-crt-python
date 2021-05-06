#!/bin/bash

set -e

if test -f "/tmp/setup_proxy_test_env.sh"; then
    source /tmp/setup_proxy_test_env.sh
fi

env

git submodule update --init

# build package
cd $CODEBUILD_SRC_DIR

python3 -m pip install .
python3 -m unittest discover test
