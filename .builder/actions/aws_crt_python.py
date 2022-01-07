
import Builder
import argparse
import json
import os.path
import pathlib
import subprocess
import sys
import tempfile


class InstallPythonReqs(Builder.Action):
    def __init__(self, trust_hosts=False, deps=[], python=sys.executable):
        self.trust_hosts = trust_hosts
        self.core = ('pip', 'setuptools', 'wheel')
        self.deps = deps
        self.python = python

    def run(self, env):
        trusted_hosts = []
        # These are necessary for older hosts with out of date certs or pip
        if self.trust_hosts:
            trusted_hosts = ['--trusted-host', 'pypi.org', '--trusted-host', 'files.pythonhosted.org']

        # setuptools must be installed before packages that need it, or else it won't be in the
        # package database in time for the subsequent install and pip fails
        steps = []
        for deps in (self.core, self.deps):
            if deps:
                steps.append([self.python, '-m', 'pip', 'install', '--upgrade', *trusted_hosts, *deps])

        return Builder.Script(steps, name='install-python-reqs')


class SetupForTests(Builder.Action):

    def run(self, env):
        self.env = env

        self._setenv_from_secret('AWS_TEST_IOT_MQTT_ENDPOINT', 'unit-test/endpoint')

        self._setenv_tmpfile_from_secret('AWS_TEST_TLS_CERT_PATH', 'unit-test/certificate', 'certificate.pem')
        self._setenv_tmpfile_from_secret('AWS_TEST_TLS_KEY_PATH', 'unit-test/privatekey', 'privatekey.pem')

        # enable S3 tests
        env.shell.setenv('AWS_TEST_S3', '1')

    def _get_secret(self, secret_id):
        """get string from secretsmanager"""

        # NOTE: using AWS CLI instead of boto3 because we know CLI is already
        # installed wherever builder is run. Once upon a time we tried using
        # boto3 by installing it while the builder was running but this didn't
        # work in some rare scenarios.

        cmd = ['aws', 'secretsmanager', 'get-secret-value', '--secret-id', secret_id]
        # NOTE: print command args, but use "quiet" mode so that output isn't printed.
        # we don't want secrets leaked to the build log
        print('>', subprocess.list2cmdline(cmd))
        result = self.env.shell.exec(*cmd, check=True, quiet=True)
        secret_value = json.loads(result.output)
        return secret_value['SecretString']

    def _tmpfile_from_secret(self, secret_name, file_name):
        """get file contents from secretsmanager, store as file under /tmp, return file path"""
        file_contents = self._get_secret(secret_name)
        file_path = os.path.join(tempfile.gettempdir(), file_name)
        print(f"Writing to: {file_path}")
        pathlib.Path(file_path).write_text(file_contents)
        return file_path

    def _setenv_from_secret(self, env_var_name, secret_name):
        """get string from secretsmanager and store in environment variable"""

        secret_value = self._get_secret(secret_name)
        self.env.shell.setenv(env_var_name, secret_value)

    def _setenv_tmpfile_from_secret(self, env_var_name, secret_name, file_name):
        """get file contents from secretsmanager, store as file under /tmp, and store path in environment variable"""
        file_path = self._tmpfile_from_secret(secret_name, file_name)
        self.env.shell.setenv(env_var_name, file_path)


class AWSCrtPython(Builder.Action):

    def run(self, env):
        # allow custom python to be used
        parser = argparse.ArgumentParser()
        parser.add_argument('--python')
        args = parser.parse_known_args(env.args.args)[0]
        python = args.python if args.python else sys.executable

        actions = [
            InstallPythonReqs(deps=[], python=python),
            SetupForTests(),
            [python, '-m', 'pip', 'install', '--verbose', '.'],
            # "--failfast" because, given how our leak-detection in tests currently works,
            # once one test fails all the rest usually fail too.
            [python, '-m', 'unittest', 'discover', '--verbose', '--failfast'],
            # http_client_test.py launches external processes using the extra args
            [python, 'crt/aws-c-http/integration-testing/http_client_test.py',
                python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
