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
# existing openssl is out of date and must be replaced to install python3
brew uninstall --ignore-dependencies openssl
if [ ! -e openssl*bottle*.tar.gz ]; then
    brew install --build-bottle openssl
    brew bottle --json openssl
    brew uninstall openssl --ignore-dependencies
fi
brew install openssl*bottle*.tar.gz

if [ ! -e sqlite*bottle*.tar.gz ]; then
    brew uninstall sqlite --ignore-dependencies
    brew install --build-bottle sqlite
    brew bottle --json sqlite
    brew uninstall sqlite --ignore-dependencies
fi
brew install sqlite*bottle*.tar.gz

# must always uninstall python2 if it's there
brew uninstall python --ignore-dependencies
if [ ! -e python*bottle*.tar.gz ]; then
    brew install --build-bottle python3
    brew bottle --json python3
    brew uninstall python3 --ignore-dependencies
fi
brew install python*bottle*.tar.gz
popd

# build dependencies
./build-deps.sh
export AWS_C_INSTALL=`pwd`/build/deps/install

# build python3 extension
python3 setup.py build
