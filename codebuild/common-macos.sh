#!/bin/bash

# Until CodeBuild supports macOS, this script is just used by Travis.

set -e
set -x

CMAKE_ARGS="$@"

# ensure each required package is installed, if not, make a bottle for brew in ./packages
# so it will be cached for future runs. If the cache is ever blown away, this will update
# the packages as well
# If the bottles are already in ./packages, then just install them
function install_from_brew {
    pushd ./packages
    # usually the existing package is too old for one of the others, so uninstall
    # and reinstall from the cache
    brew uninstall --ignore-dependencies $1
    if [ ! -e $1*bottle*.tar.gz ]; then
        brew install --build-bottle $1
        brew bottle --json $1
        brew uninstall --ignore-dependencies $1
    fi
    brew install $1*bottle*tar.gz
    popd
}

install_from_brew openssl
install_from_brew gdbm
install_from_brew python

git submodule update --init --recursive
# build dependencies
export AWS_C_INSTALL=`pwd`/build/deps/install

# build python3 extension
python3 setup.py build install
python3 elasticurl.py -v ERROR -P -H "content-type: application/json" -i -d "{'test':'testval'}" http://httpbin.org/post
python3 elasticurl.py -v ERROR -i https://example.com
python3 -m unittest tests.server_test
