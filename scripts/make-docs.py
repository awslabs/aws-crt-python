#!/usr/bin/env python3
import argparse
import os.path
from pathlib import Path
import shutil
import utils


parser = argparse.ArgumentParser()
parser.add_argument('--skip-clean', action='store_true', help="Iterate faster by skipping the clean step")
args = parser.parse_args()

utils.chdir_project_root()

# clean
if not args.skip_clean:
    docs = Path('docs')
    if docs.exists():
        shutil.rmtree(docs)
    build = Path('docsrc/build')
    if build.exists():
        shutil.rmtree(build)

# build
os.chdir('docsrc')
utils.run('make html SPHINXOPTS="-W --keep-going"')
utils.chdir_project_root()

# copy
shutil.copytree('docsrc/build/html', 'docs', dirs_exist_ok=True)

# The existence of this file tells GitHub Pages to just host the HTML as-is
# https://github.blog/2009-12-29-bypassing-jekyll-on-github-pages/
Path('docs/.nojekyll').touch()
