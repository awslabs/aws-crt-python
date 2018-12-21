#!/bin/bash

set -e
set -x

CMAKE_ARGS="$@"

git submodule update --init --recursive
export AWS_C_INSTALL=`pwd`/build/deps/install

python3 setup.py build
