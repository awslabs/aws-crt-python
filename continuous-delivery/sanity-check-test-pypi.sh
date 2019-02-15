#!/bin/bash
set -e
CURRENT_TAG_VERSION=$(git describe --abbrev=0)
python3 -m pip install -i https://testpypi.python.org/simple --user awscrt==$CURRENT_TAG_VERSION
python3 continuous-delivery/test-pip-install.py

python -m pip install -i https://testpypi.python.org/simple --user awscrt==$CURRENT_TAG_VERSION
python continuous-delivery/test-pip-install.py

