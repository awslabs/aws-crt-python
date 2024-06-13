#!/usr/bin/env python3
import utils

utils.chdir_project_root()

utils.run('python3 format-check.py -i')
utils.run('python3 scripts/format-python.py')
