#!/usr/bin/env python

import os
import re
import subprocess

tag = subprocess.check_output(['git', 'describe', '--tags'])
# strip the leading v
version = str(tag[1:].strip(), 'utf8')
setup_path = os.path.join(os.path.dirname(__file__), '..', 'setup.py')
print("Updating setup.py to version {}".format(version))
with open(setup_path, 'r+') as setup_py:
    contents = setup_py.read(64 * 1024)
    contents = re.sub(r'(\s)version=.+,', r'\1version="{}",'.format(version), contents)
    setup_py.seek(0, os.SEEK_SET)
    setup_py.write(contents)
