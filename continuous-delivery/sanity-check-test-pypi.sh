#!/bin/bash
set -ex
CURRENT_TAG_VERSION=$(git describe --tags | cut -f2 -dv)
python3 -m pip install --no-cache-dir -i https://testpypi.python.org/simple --user awscrt==$CURRENT_TAG_VERSION
python3 continuous-delivery/test-pip-install.py

python -m pip install --no-cache-dir -i https://testpypi.python.org/simple --user awscrt==$CURRENT_TAG_VERSION
python continuous-delivery/test-pip-install.py

