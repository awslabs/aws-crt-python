#!/bin/bash

# Until CodeBuild supports macOS, this script is just used by Travis.

set -e
set -x

CMAKE_ARGS="$@"
install_from_brew openssl@1.1
install_from_brew gdbm
install_from_brew sqlite
install_from_brew python

git submodule update --init --recursive
# build dependencies
export AWS_C_INSTALL=`pwd`/build/deps/install

# build python3 extension
python3 setup.py build
