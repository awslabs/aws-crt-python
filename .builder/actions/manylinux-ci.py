
import Builder
import os
import sys
from aws_crt_python import InstallPythonReqs

pythons = (
    # 'cp34-cp34m',
    'cp35-cp35m',
    'cp36-cp36m',
    'cp37-cp37m',
    'cp27-cp27m',
    'cp27-cp27mu',
)


def python_path(version):
    return '/opt/python/{}/bin/python'.format(version)


def default_python():
    return sys.executable


class ManyLinuxPackage(Builder.Action):
    def run(self, env):
        steps = []
        for version in pythons:
            python = python_path(version)
            if not os.path.isfile(python):
                print('Skipping {} as it is not installed'.format(python))
                continue
            
            actions = [
                InstallPythonReqs(python=python),
                [python,'-m', 'pip', 'install', '.',
                    '--install-option=--verbose',
                    '--install-option=sdist',
                    '--install-option=bdist_wheel'],
                ['auditwheel', 'repair', '--plat', 'manylinux1_x86_64',
                    'dist/awscrt-*{}-linux_x86_64.whl'.format(python)],
            ]
            steps.append(Builder.Script(actions, name=python))

        copy_steps = [
            ['cp', '-r', 'wheelhouse' '../dist']
            ['cp', 'dist/*.tar.gz', '../dist/']
        ]

        steps += copy_steps

        return Builder.Script(steps, name='manylinux1-package')


class ManyLinuxCI(Builder.Action):
    def run(self, env):
        python3 = default_python()

        steps = []
        for version in pythons:
            python = python_path(version)
            if not os.path.isfile(python):
                print('Skipping {} as it is not installed'.format(python))
                continue

            actions = [
                InstallPythonReqs(python=python, deps=['boto3'], trust_hosts=True),
                [python, '-m', 'pip', 'install', '.',
                    '--install-option=--verbose', '--install-option=build_ext', '--install-option=--include-dirs{openssl_include}',
                    '--install-option=--library-dirs{openssl_lib}'],
                [python3, 'aws-common-runtime/aws-c-http/integration-testing/http_client_test.py', python, 'elasticurl.py'],
            ]
            steps.append(Builder.Script(actions, name=python))

        return Builder.Script(steps, name='manylinux1-ci')
