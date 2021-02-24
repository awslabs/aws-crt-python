#!/usr/bin/env bash
set -e
pushd `dirname $0`/docsrc > /dev/null
make html
rm -rf ../docs/
cp -a build/html/. ../docs
touch ../docs/.nojekyll
popd > /dev/null
