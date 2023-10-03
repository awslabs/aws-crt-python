#!/bin/bash

set -euxo pipefail

# intentionally not pulling the submodules to make the build fail cleanly.
# git submodule update --init

export AWS_CRT_BUILD_STRICT_MODE=OFF
python -m setup.py install
python codebuild/test-config-on-failure.py
