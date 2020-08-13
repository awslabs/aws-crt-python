#!/usr/bin/env bash
set -e
pushd `dirname $0`/docsrc > /dev/null
make html
cp -a build/html/. ../docs
popd > /dev/null
