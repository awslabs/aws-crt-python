#!/usr/bin/env bash
set -e

pushd `dirname $0` > /dev/null

# clean
rm -rf docs/
rm -rf docsrc/build/

# build
pushd docsrc > /dev/null
make html SPHINXOPTS="-W --keep-going"
popd > /dev/null

cp -a docsrc/build/html/. docs

popd > /dev/null
