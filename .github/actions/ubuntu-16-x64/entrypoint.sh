#!/bin/sh

set -ex

cd $GITHUB_WORKSPACE
python3 -c "from urllib.request import urlretrieve; urlretrieve('https://raw.githubusercontent.com/awslabs/aws-c-common/master/codebuild/builder.py', 'builder.py')"
python3 -m virtualenv venv
python="./venv/bin/python"
$python builder.py build $1

