import Builder
import argparse
import os

# Fall back on using the "{python}" builder variable
PYTHON_DEFAULT = '{python}'


class AWSCrtPython(Builder.Action):
    python = PYTHON_DEFAULT

    # Some CI containers have pip installed via "rpm" or non-Python methods, and this causes issues when
    # we try to update pip via "python -m pip install --upgrade" because there are no RECORD files present.
    # Therefore, we have to seek alternative ways with a last resort of installing with "--ignore-installed"
    # if nothing else works AND the builder is running in GitHub actions.
    # As of writing, this is primarily an issue with the AL2-x64 image.
    def try_to_upgrade_pip(self, env):
        did_upgrade = False
        try:
            Builder.Script([[self.python, '-m', 'pip', 'install', '--upgrade', 'pip']]).run(env)
            did_upgrade = True
        except Exception:
            print("Could not update pip via normal pip upgrade. Next trying via package manager...")

        if (did_upgrade == False):
            try:
                Builder.Script([Builder.InstallPackages(['pip'],)]).run(env)
                did_upgrade = True
            except Exception:
                print("Could not update pip via package manager. Next resorting to forcing an ignore install...")

        if (did_upgrade == False):
            # Only run in GitHub actions by checking for specific environment variable
            # Source: https://docs.github.com/en/actions/learn-github-actions/variables#default-environment-variables
            if (os.getenv("GITHUB_ACTIONS") is not None):
                try:
                    Builder.Script([[self.python, '-m', 'pip', 'install', '--upgrade',
                                   '--ignore-installed', 'pip']]).run(env)
                except Exception as ex:
                    print("Could not update pip via ignore install! Something is terribly wrong!")
                    raise (ex)
                did_upgrade = True
            else:
                print("Not on GitHub actions - skipping reinstalling Pip. Update/Install pip manually and rerun the builder")

    def run(self, env):
        # allow custom python to be used
        parser = argparse.ArgumentParser()
        parser.add_argument('--python')
        args = parser.parse_known_args(env.args.args)[0]
        self.python = args.python if args.python else PYTHON_DEFAULT

        # Enable S3 tests
        env.shell.setenv('AWS_TEST_S3', '1')

        actions = [
            # Upgrade Pip via a number of different methods
            self.try_to_upgrade_pip,
            [self.python, '-m', 'pip', 'install', '--upgrade', '--requirement', 'requirements-dev.txt'],
            Builder.SetupCrossCICrtEnvironment(),
            [self.python, '-m', 'pip', 'install', '--verbose', '.'],
            # "--failfast" because, given how our leak-detection in tests currently works,
            # once one test fails all the rest usually fail too.
            [self.python, '-m', 'unittest', 'discover', '--verbose', '--failfast'],
            # http_client_test.py launches external processes using the extra args
            [self.python, 'crt/aws-c-http/integration-testing/http_client_test.py',
                self.python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
