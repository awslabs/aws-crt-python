
import Builder
import os
import sys


class InstallPythonReqs(Builder.Action):
    def __init__(self, trust_hosts=False, deps=[], python=sys.executable):
        self.trust_hosts = trust_hosts
        self.core = ('pip', 'setuptools', 'virtualenv')
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
            steps.append([self.python, '-m', 'pip', 'install', '--upgrade', *trusted_hosts, *deps])

        return Builder.Script(steps, name='install-python-reqs')


class AWSCrtPython(Builder.Action):
    def __init__(self, python=None):
        """
        Prefer the current python3 executable (so that venv is used),
        but allow a custom python to be passed for installing and testing awscrt.
        """
        self.python3 = sys.executable
        self.python = python if python else self.python3

    def run(self, env):
        install_options = []
        if 'linux' == Builder.Host.current_platform():
            install_options = [
                '--install-option=--include-dirs={openssl_include}',
                '--install-option=--library-dirs={openssl_lib}']

        actions = [
            InstallPythonReqs(deps=['boto3'], python=self.python),
            [self.python, '-m', 'pip', 'install', '.', '--install-option=--verbose',
                '--install-option=build_ext', *install_options],
            [self.python, '-m', 'unittest', 'discover', '--verbose'],
            # http_client_test.py is python3-only, but launches external processes using the extra args
            [self.python3, 'aws-common-runtime/aws-c-http/integration-testing/http_client_test.py', self.python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
