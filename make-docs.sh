#!/usr/bin/env bash
set -e
pushd `dirname $0`/docsrc > /dev/null
rm -rf build/
make html SPHINXOPTS="-W --keep-going"
rm -rf ../docs/
cp -a build/html/. ../docs
touch ../docs/.nojekyll
popd > /dev/null
