#!/bin/bash

# Until CodeBuild supports macOS, this script is just used by Travis.

set -e
set -x

CMAKE_ARGS="$@"

# ensure each required package is installed, if not, make a bottle for brew in ./packages
# so it will be cached for future runs. If the cache is ever blown away, this will update
# the packages as well
# If the bottles are already in ./packages, then just install them
pushd ./packages
brew uninstall --ignore-dependencies openssl
if [ ! -e openssl*bottle*.tar.gz ]; then
    brew install --build-bottle openssl
    brew bottle --json openssl
    brew uninstall openssl
fi
brew install openssl*bottle*.tar.gz

if [ ! -e python3*bottle*.tar.gz ]; then
    brew install --build-bottle python3
    brew bottle --json python3
    brew uninstall python3
fi
brew install python3*bottle*.tar.gz
popd

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
