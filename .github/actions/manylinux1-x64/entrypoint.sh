#!/bin/sh

set -ex

python=/opt/python/cp37-cp37m/bin/python

cd $GITHUB_WORKSPACE
$python -c "from urllib.request import urlretrieve; urlretrieve('https://raw.githubusercontent.com/awslabs/aws-c-common/builder2/codebuild/builder.py', 'builder.py')"
$python builder.py run $1

