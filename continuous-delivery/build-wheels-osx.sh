#!/bin/bash
#before running this, you'll need cmake3 and a compiler. These python versions are just
#using the default python installers from python.org. Each version needs updated: pip, build
set -ex

/Library/Frameworks/Python.framework/Versions/3.9/bin/python3 ./continuous-delivery/update-version.py

/Library/Frameworks/Python.framework/Versions/3.8/bin/python3 -m build
/Library/Frameworks/Python.framework/Versions/3.9/bin/python3 -m build
/Library/Frameworks/Python.framework/Versions/3.10/bin/python3 -m build
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 -m build

# Don't need to build wheels for Python 3.12, it works with the 3.11 stable ABI wheel

# We are using the Python 3.13 stable ABI from Python 3.13 onwards because of deprecated functions.
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m build

# The free-threaded build does not currently support the Limited C API or the stable ABI. Built them separately
/Library/Frameworks/PythonT.framework/Versions/3.13/bin/python3.13t -m build
/Library/Frameworks/PythonT.framework/Versions/3.14/bin/python3.14t -m build

#now you just need to run twine (that's in a different script)
