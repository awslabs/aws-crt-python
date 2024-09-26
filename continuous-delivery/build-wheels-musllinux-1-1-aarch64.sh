#!/bin/bash
#assumes image based on musllinux_1_1
set -ex

/opt/python/cp39-cp39/bin/python ./continuous-delivery/update-version.py

/opt/python/cp38-cp38/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_aarch64 dist/awscrt-*cp38*.whl

/opt/python/cp39-cp39/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_aarch64 dist/awscrt-*cp39*.whl

/opt/python/cp310-cp310/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_aarch64 dist/awscrt-*cp310*.whl

/opt/python/cp311-cp311/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_aarch64 dist/awscrt-*cp311*.whl

# Don't need to build wheels for Python 3.12.
# The 3.11 wheel uses the stable ABI, so it works with newer versions too.

# We are using the Python 3.13 stable ABI from Python 3.13 onwards because of deprecated functions.
/opt/python/cp313-cp313/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_aarch64 dist/awscrt-*cp313*.whl

rm dist/*.whl
cp -rv wheelhouse/* dist/

#now you just need to run twine (that's in a different script)
