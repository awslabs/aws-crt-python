import Builder
import argparse

# Fall back on using the "{python}" builder variable
PYTHON_DEFAULT = '{python}'


class AWSCrtPython(Builder.Action):

    def run(self, env):
        # allow custom python to be used
        parser = argparse.ArgumentParser()
        parser.add_argument('--python')
        args = parser.parse_known_args(env.args.args)[0]
        python = args.python if args.python else PYTHON_DEFAULT

        # Enable S3 tests
        env.shell.setenv('AWS_TEST_S3', '1')

        actions = [
            # Force-reinstall Pip because some CI containers (al2-x64 being one) have Pip installed without
            # a RECORD file and therefore it will not be able to uninstall via a normal upgrade call.
            [python, '-m', 'pip', 'install', '--upgrade', '--force-reinstall', 'pip'],
            [python, '-m', 'pip', 'install', '--upgrade', '--requirement', 'requirements-dev.txt'],
            Builder.SetupCrossCICrtEnvironment(),
            [python, '-m', 'pip', 'install', '--verbose', '.'],
            # "--failfast" because, given how our leak-detection in tests currently works,
            # once one test fails all the rest usually fail too.
            [python, '-m', 'unittest', 'discover', '--verbose', '--failfast'],
            # http_client_test.py launches external processes using the extra args
            [python, 'crt/aws-c-http/integration-testing/http_client_test.py',
                python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
