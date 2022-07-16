#!/usr/bin/env python3
import utils

FILES_AND_FOLDERS_TO_FORMAT = [
    '.builder/',
    'awscrt/',
    'scripts/',
    'test/',
    'setup.py',
]

utils.chdir_project_root()

utils.run(['python3',
           '-m', 'autopep8',
           '--in-place',  # edit files in place
           '--recursive',
           '--jobs', '0',  # parallel with all CPUs
           *FILES_AND_FOLDERS_TO_FORMAT])
