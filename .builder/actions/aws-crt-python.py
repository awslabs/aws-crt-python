
import Builder
import os

class AWSCrtPython(Builder.Action):
    def run(self, env):        
        # Once the virtualenv is set up, we must use that python, so that the venv is used
        venv_python = os.path.join('.', 'venv', 'bin', 'python')

        actions = [
            ['git', 'submodule', 'update', '--init', '--recursive'],
            ['sudo', '{python}', '-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'virtualenv'],
            ['{python}', '-m', 'virtualenv', 'venv'],
            [venv_python, '-m', 'pip', 'install', '--upgrade', 'autopep8', 'boto3'],
            [venv_python, '-m', 'pip', 'install', '.', '--install-option=--verbose', '--install-option=build_ext', '--install-option=--include-dirs{openssl_include}', '--install-option=--library-dirs{openssl_lib}'],
            [venv_python, '-m', 'unittest', 'discover', '--verbose'],
            [venv_python, 'aws-common-runtime/aws-c-http/integration-testing/http_client_test.py', venv_python, 'elasticurl.py'],
            [venv_python, '-m', 'autopep8', '--exit-code', '--diff', '--recursive', 'awscrt', 'test', 'setup.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
