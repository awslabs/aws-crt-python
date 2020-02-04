
import Builder
import os, sys

class AWSCrtPython(Builder.Action):
    def run(self, env):        
        # Once the virtualenv is set up, we must use that python, so that the venv is used
        python = sys.executable

        actions = [
            ['git', 'submodule', 'update', '--init', '--recursive'],
            [python, '-m', 'pip', 'install', '--upgrade', 'autopep8', 'boto3'],
            [python, '-m', 'pip', 'install', '.', '--install-option=--verbose', '--install-option=build_ext', '--install-option=--include-dirs{openssl_include}', '--install-option=--library-dirs{openssl_lib}'],
            [python, '-m', 'unittest', 'discover', '--verbose'],
            [python, 'aws-common-runtime/aws-c-http/integration-testing/http_client_test.py', python, 'elasticurl.py'],
            [python, '-m', 'autopep8', '--exit-code', '--diff', '--recursive', 'awscrt', 'test', 'setup.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
