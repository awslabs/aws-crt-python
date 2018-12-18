#!/bin/bash

set -e
set -x

CMAKE_ARGS="$@"

function install_library {
    git clone https://github.com/awslabs/$1.git
    pushd $1

    if [ -n "$2" ]; then
        git checkout $2
    fi

    mkdir dep-build
    cd dep-build

    cmake -DCMAKE_INSTALL_PREFIX=$AWS_C_INSTALL $CMAKE_ARGS ../
    make install
    popd
}

export AWS_C_INSTALL=`pwd`/build/deps/install

# Linux needs s2n
install_library s2n

./build-deps.sh $CMAKE_ARGS

python3 setup.py build
