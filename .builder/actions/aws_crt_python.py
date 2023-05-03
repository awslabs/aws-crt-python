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
            # We force install pip because some containers cannot uninstall and upgrade pip, but we need a newer
            # pip for setuptools. Not ideal, but gets the job done.
            [python, '-m', 'pip', 'install', '--upgrade', '--ignore-installed', 'pip'],
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
