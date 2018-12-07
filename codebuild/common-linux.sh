#!/bin/bash

set -e

CMAKE_ARGS="$@"

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

mkdir -p install
export AWS_C_INSTALL=`pwd`/install

# If TRAVIS_OS_NAME is OSX, skip this step (will resolve to empty string on CodeBuild)
if [ "$TRAVIS_OS_NAME" != "osx" ]; then
    sudo apt-get install libssl-dev -y
    install_library s2n 7c9069618e68214802ac7fbf45705d5f8b53135f
fi
install_library aws-c-common
install_library aws-c-io
install_library aws-c-mqtt transactional-tree

cd aws-crt-python

python3 setup.py build
