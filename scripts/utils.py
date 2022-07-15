import os
import subprocess
import sys


def run(args: str | list[str]):
    # ensure proper python executable is being used
    if isinstance(args, list):
        if args[0] == 'python3':
            args[0] = sys.executable
    else:  # args is str
        if args.startswith('python3'):
            args = args.replace('python3', sys.executable)

    # run
    result = subprocess.run(args)
    if result.returncode != 0:
        sys.exit('FAILED')


def chdir_project_root():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    os.chdir(root)
