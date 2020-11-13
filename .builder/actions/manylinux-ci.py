
import Builder
import os
import sys
from aws_crt_python import AWSCrtPython, InstallPythonReqs

pythons = (
    'cp35-cp35m',
    'cp36-cp36m',
    'cp37-cp37m',
    'cp38-cp38',
    'cp39-cp39',
)


def python_path(version):
    return '/opt/python/{}/bin/python'.format(version)


class ManyLinuxPackage(Builder.Action):
    def run(self, env):
        steps = []
        for version in pythons:
            python = python_path(version)
            if not os.path.isfile(python):
                print('Skipping {} as it is not installed'.format(python))
                continue

            install_options = []
            if 'linux' == Builder.Host.current_platform():
                install_options = [
                    '--install-option=--include-dirs={openssl_include}',
                    '--install-option=--library-dirs={openssl_lib}']

            actions = [
                InstallPythonReqs(python=python),
                [python, '-m', 'pip', 'install', '.',
                    '--install-option=--verbose',
                    '--install-option=sdist',
                    '--install-option=bdist_wheel',
                    *install_options],
                ['auditwheel', 'repair', '--plat', 'manylinux1_x86_64',
                    'dist/awscrt-*{}-linux_x86_64.whl'.format(python)],
            ]
            steps.append(Builder.Script(actions, name=python))

        copy_steps = [
            ['cp', '-r', 'wheelhouse', '../dist'],
            ['cp', 'dist/*.tar.gz', '../dist/']
        ]

        steps += copy_steps

        return Builder.Script(steps, name='manylinux-package')


class ManyLinuxCI(Builder.Action):
    def run(self, env):
        steps = []
        for version in pythons:
            python = python_path(version)
            if not os.path.isfile(python):
                print('Skipping {} as it is not installed'.format(python))
                continue

            # Run the usual AWSCrtPython build and test steps for this python
            steps.append(AWSCrtPython(custom_python=python, name=python))

        return Builder.Script(steps, name='manylinux-ci')
