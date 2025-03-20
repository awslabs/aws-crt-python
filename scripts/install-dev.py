#!/usr/bin/env python3
import utils

utils.chdir_project_root()

utils.run('python3 -m pip install --verbose --editable ".[dev]"')
