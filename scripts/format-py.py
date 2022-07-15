#!/usr/bin/env python3
import utils

utils.chdir_project_root()

files_and_folders_to_format = [
    '.builder/',
    'awscrt/',
    'scripts/',
    'test/',
    'setup.py',
]

utils.run(['python3',
           '-m', 'autopep8',
           '--in-place',  # edit files in place
           '--recursive',
           '--jobs', '0',  # parallel with all CPUs
           *files_and_folders_to_format])
