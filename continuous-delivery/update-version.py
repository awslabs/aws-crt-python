#!/usr/bin/env python3

import os
import re
import subprocess

tag = subprocess.run(['git', 'describe', '--tags'],
                     capture_output=True, check=True,
                     text=True).stdout.strip()
# convert v0.2.12-2-g50254a9 to 0.2.12
# test-version-exists will ensure to not include non-tagged commits
version = tag[1:].strip("v").split('-', 1)[0]

init_path = os.path.join(os.path.dirname(__file__), '..', 'awscrt', '__init__.py')
print("Updating awscrt.__version__ to version {}".format(version))
contents = None
with open(init_path, 'r+') as init_py:
    contents = init_py.read()

contents = re.sub(r"__version__ = '[^']+'", f"__version__ = '{version}'", contents)

with open(init_path, 'w') as init_py:
    init_py.write(contents)
