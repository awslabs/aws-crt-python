#!/bin/bash
#before running this, you'll need cmake3 and a compiler. These python versions are just
#using the default python installers from python.org. Each version needs updated pip, wheel, and setuptools
set -ex

/Library/Frameworks/Python.framework/Versions/3.9/bin/python3 ./continuous-delivery/update-version.py

/Library/Frameworks/Python.framework/Versions/3.7/bin/python3 setup.py sdist bdist_wheel
/Library/Frameworks/Python.framework/Versions/3.8/bin/python3 setup.py sdist bdist_wheel
/Library/Frameworks/Python.framework/Versions/3.9/bin/python3 setup.py sdist bdist_wheel
/Library/Frameworks/Python.framework/Versions/3.10/bin/python3 setup.py sdist bdist_wheel
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 setup.py sdist bdist_wheel

#now you just need to run twine (that's in a different script)
