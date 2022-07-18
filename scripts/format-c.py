#!/usr/bin/env python3
import utils
import glob

FILE_PATTERNS = [
    'source/**/*.h',
    'source/**/*.c',
]

utils.chdir_project_root()

files = []
for pattern in FILE_PATTERNS:
    files.extend(glob.glob(pattern, recursive=True))

utils.run(['clang-format', '-i', *files])
