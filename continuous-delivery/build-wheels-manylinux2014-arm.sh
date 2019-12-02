#!/bin/bash
#before running this, you'll need cmake3 and a compiler. These python versions are just
#using the default python installers from python.org. Each version needs updated pip, wheel, and setuptools
set -e
/usr/local/bin/python3.5m setup.py sdist bdist_wheel
auditwheel repair --plat manylinux2014_aarch64 dist/awscrt-*cp35*.whl

/usr/local/bin/python3.6m setup.py sdist bdist_wheel
auditwheel repair --plat manylinux2014_aarch64 dist/awscrt-*cp36*.whl

/usr/local/bin/python3.7m setup.py sdist bdist_wheel
auditwheel repair --plat manylinux2014_aarch64 dist/awscrt-*cp37*.whl

/usr/local/bin/python3.8 setup.py sdist bdist_wheel
auditwheel repair --plat manylinux2014_aarch64 dist/awscrt-*cp38*.whl

rm dist/*.whl
cp -r wheelhouse/* dist/

#now you just need to run twine (that's in a different script)

