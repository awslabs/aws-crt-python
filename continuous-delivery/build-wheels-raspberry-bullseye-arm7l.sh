#!/bin/bash
#assumes image based on manylinux2014 + extras (cmake3, libcrypto, etc)
set -ex

export CC=gcc
python3 ./continuous-delivery/update-version.py

python3.6 setup.py sdist bdist_wheel

python3.7 setup.py sdist bdist_wheel

python3.9 setup.py sdist bdist_wheel

python3.8 setup.py sdist bdist_wheel

python3.10 setup.py sdist bdist_wheel


rm dist/*.whl
cp -rv wheelhouse/* dist/

#now you just need to run twine (that's in a different script)
