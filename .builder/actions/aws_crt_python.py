import Builder
import argparse
from pathlib import Path
import sys


class AWSCrtPython(Builder.Action):

    def run(self, env):
        # allow custom python to be used
        parser = argparse.ArgumentParser()
        parser.add_argument('--python')
        args = parser.parse_known_args(env.args.args)[0]
        if args.python:
            self.python = args.python
        else:
            # Fall back on using the "{python}" builder variable
            self.python = env.config['variables']['python']

        # Create a virtual environment and use that.
        # Otherwise, in places like ubuntu 24.04, PEP 668 stops
        # you from globally installing/upgrading packages
        venv_dirpath = Path.cwd() / '.venv-builder'
        env.shell.exec(self.python, '-m', 'venv', str(venv_dirpath), check=True)
        if sys.platform == 'win32':
            self.python = str(venv_dirpath / 'Scripts/python')
        else:
            self.python = str(venv_dirpath / 'bin/python')

        # Enable S3 tests
        env.shell.setenv('AWS_TEST_S3', '1')
        env.shell.setenv('MACOS_DEPLOYMENT_TARGET', '10.15')

        actions = [
            [self.python, '--version'],
            [self.python, '-m', 'pip', 'install', '--upgrade', 'pip'],
            Builder.SetupCrossCICrtEnvironment(),
            [self.python, '-m', 'pip', 'install', '--verbose', '.[dev]'],
            # "--failfast" because, given how our leak-detection in tests currently works,
            # once one test fails all the rest usually fail too.
            [self.python, '-m', 'unittest', 'discover', '--verbose', '--failfast'],
            # http_client_test.py launches external processes using the extra args
            [self.python, 'crt/aws-c-http/integration-testing/http_client_test.py',
                self.python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
