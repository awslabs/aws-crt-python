
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
    def __init__(self, custom_python=None, name=None):
        """
        Prefer the current python3 executable (so that venv is used).
        But allow a custom python to be used for installing and testing awscrt on.
        """
        self.python3 = sys.executable
        self.custom_python = custom_python if custom_python else self.python3
        self.name = name if name else 'aws-crt-python'

    def run(self, env):
        install_options = []
        if 'linux' == Builder.Host.current_os():
            install_options = [
                '--install-option=--include-dirs={openssl_include}',
                '--install-option=--library-dirs={openssl_lib}']

        actions = [
            InstallPythonReqs(deps=['boto3'], python=self.custom_python),
            [self.custom_python, '-m', 'pip', 'install', '--install-option=--verbose',
                '--install-option=build_ext', *install_options],
            [self.custom_python, '-m', 'unittest', 'discover', '--verbose'],
            # http_client_test.py is python3-only. It launches external processes using the extra args
            [self.python3, 'aws-common-runtime/aws-c-http/integration-testing/http_client_test.py',
                self.custom_python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name=self.name)
