#!/bin/sh

set -ex

cd $GITHUB_WORKSPACE
python3 -m virtualenv venv
python="./venv/bin/python"
$python builder.py build $1

