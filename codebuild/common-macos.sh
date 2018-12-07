#!/bin/bash

# Until CodeBuild supports macOS, this script is just used by Travis.

set -e

CMAKE_ARGS="$@"

brew install python3

function install_library {
    git clone https://github.com/awslabs/$1.git
    cd $1

    if [ -n "$2" ]; then
        git checkout $2
    fi

    mkdir build
    cd build

    cmake -DCMAKE_INSTALL_PREFIX=$AWS_C_INSTALL -DENABLE_SANITIZERS=ON $CMAKE_ARGS ../
    make install

    cd ../..
}

cd ../

mkdir install
export AWS_C_INSTALL=`pwd`/install

install_library aws-c-common
install_library aws-c-io
install_library aws-c-mqtt

cd aws-crt-python

python3 setup.py build
