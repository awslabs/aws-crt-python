#!/bin/bash
#assumes image based on musllinux_1_1 + extras (pip)
set -ex

/opt/python/cp39-cp39/bin/python ./continuous-delivery/update-version.py

/opt/python/cp37-cp37m/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_x86_64 dist/awscrt-*cp37*.whl

/opt/python/cp38-cp38/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_x86_64 dist/awscrt-*cp38*.whl

/opt/python/cp39-cp39/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_x86_64 dist/awscrt-*cp39*.whl

/opt/python/cp310-cp310/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_x86_64 dist/awscrt-*cp310*.whl

/opt/python/cp311-cp311/bin/python setup.py sdist bdist_wheel
auditwheel repair --plat musllinux_1_1_x86_64 dist/awscrt-*cp311*.whl

rm dist/*.whl
cp -rv wheelhouse/* dist/

#now you just need to run twine (that's in a different script)
