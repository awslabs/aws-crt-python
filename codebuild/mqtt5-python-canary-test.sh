#!/bin/bash

set -euxo pipefail

env

git submodule update --init

# build package
cd $CODEBUILD_SRC_DIR

export AWS_TEST_S3=YES
python -m pip install --verbose .
python codebuild/CanaryWrapper.py --canary_executable $CANNARY_TEST_EXE --canary_arguments "-s ${CANARY_DURATION} -t ${CANARY_THREADS} -T ${CANARY_TPS} -C ${CANARY_CLIENT_COUNT} -v ${CANARY_LOG_LEVEL} endpoint ${ENDPOINT}" --git_hash ${GIT_HASH} --git_repo_name $PACKAGE_NAME --codebuild_log_path $CODEBUILD_LOG_PATH
# python -m unittest --failfast --verbose 2>&1 | tee /tmp/tests.log test.test_mqtt5_canary
