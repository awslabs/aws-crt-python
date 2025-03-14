#!/usr/bin/env python3
import glob
import os
import shutil
import utils

# apply these patterns without recursing through subfolders
NONRECURSIVE_PATTERNS = [
    'build/',
    '_awscrt*.*',  # compiled _awscrt shared lib
    '*.egg-info/',
    'dist/',
    'wheelhouse/',
    'docsrc/build/',
]

# recurse through subfolders and apply these patterns
RECURSIVE_PATTERNS = [
    '*.pyc',
    '__pycache__'
]

# approved list of folders
# because we don't want to clean the virtual environment folder
APPROVED_RECURSIVE_FOLDERS = [
    'awscrt',
    'scripts',
    'test',
    '.builder',
]

utils.chdir_project_root()

utils.run('python3 -m pip uninstall -y awscrt')

paths = []
for pattern in NONRECURSIVE_PATTERNS:
    paths.extend(glob.glob(pattern))

for pattern in RECURSIVE_PATTERNS:
    for folder in APPROVED_RECURSIVE_FOLDERS:
        paths.extend(glob.glob(f'{folder}/**/{pattern}', recursive=True))

for path in paths:
    print(f'delete: {path}')
    if os.path.isfile(path):
        os.remove(path)
    else:
        shutil.rmtree(path)
