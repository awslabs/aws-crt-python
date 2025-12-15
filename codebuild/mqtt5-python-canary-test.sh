#!/bin/bash

set -euxo pipefail

env

git submodule update --init

# build package
cd $CODEBUILD_SRC_DIR

python -m pip install --verbose .
python codebuild/CanaryWrapper.py --canary_executable 'python test/mqtt5_canary.py' --git_hash ${GIT_HASH} --git_repo_name $PACKAGE_NAME --codebuild_log_path $CODEBUILD_LOG_PATH --ticket_item "IoT SDK for Python" --cloudwatch_namespace mqtt5_canary
