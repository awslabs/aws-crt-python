#!/bin/bash
#before running this, you'll need cmake3 and a compiler. These python versions are just
#using the default python installers from python.org. Each version needs updated pip, wheel, and setuptools
set -e
/Library/Frameworks/Python.framework/Versions/2.7/bin/python setup.py bdist_wheel
#note python 3.3 on OSX is a no-go, there's no installer. If you can build python 3.3 from source
# you can build the wheel, easy-peasy
/Library/Frameworks/Python.framework/Versions/3.4/bin/python3 setup.py bdist_wheel
/Library/Frameworks/Python.framework/Versions/3.5/bin/python3 setup.py bdist_wheel
/Library/Frameworks/Python.framework/Versions/3.6/bin/python3 setup.py bdist_wheel
/Library/Frameworks/Python.framework/Versions/3.7/bin/python3 setup.py sdist bdist_wheel
#now you just need to run twine (that's in a different script)
