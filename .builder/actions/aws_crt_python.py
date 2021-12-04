
import Builder
import argparse
import os.path
import pathlib
import subprocess
import sys
import tempfile


class InstallPythonReqs(Builder.Action):
    def __init__(self, trust_hosts=False, deps=[], python=sys.executable):
        self.trust_hosts = trust_hosts
        self.core = ('pip', 'setuptools')
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
            steps.append([self.python, '-m', 'pip', 'install', *trusted_hosts, *deps])

        return Builder.Script(steps, name='install-python-reqs')


class SetupForTests(Builder.Action):

    def run(self, env):
        # we want to use boto3 to pull data from secretsmanager
        # boto3 might need to be installed first...
        try:
            import boto3
        except BaseException:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'boto3'])
            import boto3

        secrets = boto3.client('secretsmanager')

        # get string from secretsmanager and store in environment variable
        def setenv_from_secret(env_var_name, secret_name):
            response = secrets.get_secret_value(SecretId=secret_name)
            env.shell.setenv(env_var_name, response['SecretString'])

        # get file contents from secretsmanager, store as file under /tmp
        # and store path in environment variable
        def setenv_tmpfile_from_secret(env_var_name, secret_name, file_name):
            response = secrets.get_secret_value(SecretId=secret_name)
            file_contents = response['SecretString']
            file_path = os.path.join(tempfile.gettempdir(), file_name)
            pathlib.File(file_path).write_text(file_contents)
            env.shell.setenv(env_var_name, file_path)

        setenv_from_secret('AWS_TEST_IOT_MQTT_ENDPOINT', 'unit-test/endpoint')

        setenv_tmpfile_from_secret('AWS_TEST_TLS_CERT_PATH', 'unit-test/certificate', 'certificate.pem')
        setenv_tmpfile_from_secret('AWS_TEST_TLS_KEY_PATH', 'unit-test/privatekey', 'privatekey.pem')

        # tests must run with leak detection turned on
        env.shell.setenv('AWS_CRT_MEMORY_TRACING', '2')


class AWSCrtPython(Builder.Action):

    def run(self, env):
        # allow custom python to be used
        parser = argparse.ArgumentParser()
        parser.add_argument('--python')
        args = parser.parse_known_args(env.args.args)[0]
        python = args.python if args.python else sys.executable

        actions = [
            InstallPythonReqs(deps=['boto3'], python=python),
            [python, '-m', 'pip', 'install', '--verbose', '.'],
            SetupForTests(python=python),
            # "--failfast" because, given how our leak-detection in tests currently works,
            # once one test fails all the rest usually fail too.
            [python, '-m', 'unittest', 'discover', '--verbose', '--failfast'],
            # http_client_test.py launches external processes using the extra args
            [python, 'crt/aws-c-http/integration-testing/http_client_test.py',
                python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
