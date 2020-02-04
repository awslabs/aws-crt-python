
import Builder
import os, sys

pythons = (
    #'cp34-cp34m',
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

class ManyLinux1Package(Builder.Action):
    def run(self, env):        
        steps = []
        for version in pythons:
            python = python_path(version)
            actions = [
                [python, '-m', 'pip', 'install', '--upgrade', 'autopep8', 'boto3'],
                [python, '-m', 'pip', 'install', '.', '--install-option=--verbose', '--install-option=sdist', '--install-option=bdist_wheel'],
                ['auditwheel', 'repair', '--plat', 'manylinux1_x86_64', 'dist/awscrt-*{}-linux_x86_64.whl'.format(python)],
                
                [venv_python, 'aws-common-runtime/aws-c-http/integration-testing/http_client_test.py', venv_python, 'elasticurl.py'],
                [venv_python, '-m', 'autopep8', '--exit-code', '--diff', '--recursive', 'awscrt', 'test', 'setup.py'],
            ]
            steps.append(Builder.Script(actions, name=python))

        copy_steps = [
            ['cp', '-r', 'wheelhouse' '../dist']
            ['cp', 'dist/*.tar.gz', '../dist/']
        ]
            
        steps += copy_steps

        return Builder.Script(steps, name='manylinux1-package')

class ManyLinux1CI(Builder.Action):
    def run(self, env):
        steps = []
        for version in pythons:
            python = python_path(version)
            python3 = default_python()
            actions = [
                [python, '-m', 'pip', 'install', '--upgrade',
                    "--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org",
                    "pip", "setuptools", "boto3", "autopep8"],
                [python, '-m', 'pip', 'install', '.',
                    '--install-option=--verbose', '--install-option=build_ext', '--install-option=--include-dirs{openssl_include}',
                    '--install-option=--library-dirs{openssl_lib}'],
                [python3, 'aws-common-runtime/aws-c-http/integration-testing/http_client_test.py', python, 'elasticurl.py'],
                [python3, '-m', 'autopep8', '--exit-code', '--diff', '--recursive', 'awscrt', 'test', 'setup.py'],
            ]
            steps.append(Builder.Script(actions, name=python))

        return Builder.Script(steps, name='manylinux1-ci')
