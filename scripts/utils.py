import os
import shlex
import subprocess
import sys


def run(args: str | list[str]):
    """
    Run a program.

    args may be a string, or list of argument strings.

    If the program is "python3", this is replaced with the
    full path to the current python executable.
    """

    # convert string to list
    # so that we don't need to pass shell=True to subprocess.run()
    # because turning on shell can mess things up (i.e. clang-format hangs forever for some reason)
    if isinstance(args, str):
        args = shlex.split(args)

    # ensure proper python executable is used
    if args[0] == 'python3':
        args[0] = sys.executable

    # run
    print(f'+ {subprocess.list2cmdline(args)}')
    result = subprocess.run(args)
    if result.returncode != 0:
        sys.exit('FAILED')


def chdir_project_root():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    os.chdir(root)
