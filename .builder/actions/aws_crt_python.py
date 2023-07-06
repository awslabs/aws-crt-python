import Builder
import argparse
import os
import sys

# Fall back on using the "{python}" builder variable
PYTHON_DEFAULT = '{python}'


class SetupForTests(Builder.Action):

    def run(self, env):
        self.env = env

        self._setenv_from_secret('AWS_TEST_IOT_MQTT_ENDPOINT', 'unit-test/endpoint')
        self._setenv_from_secret('AWS_TESTING_COGNITO_IDENTITY', 'aws-c-auth-testing/cognito-identity')

        self._setenv_tmpfile_from_secret('AWS_TEST_TLS_CERT_PATH', 'unit-test/certificate', 'certificate.pem')
        self._setenv_tmpfile_from_secret('AWS_TEST_TLS_KEY_PATH', 'unit-test/privatekey', 'privatekey.pem')

        self._setenv_tmpfile_from_secret('AWS_TEST_ECC_CERT_PATH', 'ecc-test/certificate', 'ECCcertificate.pem')
        self._setenv_tmpfile_from_secret('AWS_TEST_ECC_KEY_PATH', 'ecc-test/privatekey', 'ECCprivatekey.pem')

        self._setenv_from_secret('AWS_TEST_MQTT5_IOT_CORE_HOST', 'unit-test/endpoint')
        self._setenv_tmpfile_from_secret(
            'AWS_TEST_MQTT5_IOT_KEY_PATH',
            'ci/mqtt5/us/Mqtt5Prod/key',
            'mqtt5certificate.pem')
        self._setenv_tmpfile_from_secret(
            'AWS_TEST_MQTT5_IOT_CERTIFICATE_PATH',
            'ci/mqtt5/us/Mqtt5Prod/cert',
            'mqtt5privatekey.pem')

        # enable S3 tests
        env.shell.setenv('AWS_TEST_S3', '1')

        self._try_setup_pkcs11()

    def _get_secret(self, secret_id):
        """get string from secretsmanager"""

        # NOTE: using AWS CLI instead of boto3 because we know CLI is already
        # installed wherever builder is run. Once upon a time we tried using
        # boto3 by installing it while the builder was running but this didn't
        # work in some rare scenarios.

        cmd = ['aws', 'secretsmanager', 'get-secret-value', '--secret-id', secret_id]
        # NOTE: print command args, but use "quiet" mode so that output isn't printed.
        # we don't want secrets leaked to the build log
        print('>', subprocess.list2cmdline(cmd))
        result = self.env.shell.exec(*cmd, check=True, quiet=True)
        secret_value = json.loads(result.output)
        return secret_value['SecretString']

    def _tmpfile_from_secret(self, secret_name, file_name):
        """get file contents from secretsmanager, store as file under /tmp, return file path"""
        file_contents = self._get_secret(secret_name)
        file_path = os.path.join(tempfile.gettempdir(), file_name)
        print(f"Writing to: {file_path}")
        pathlib.Path(file_path).write_text(file_contents)
        return file_path

    def _setenv_from_secret(self, env_var_name, secret_name):
        """get string from secretsmanager and store in environment variable"""

        secret_value = self._get_secret(secret_name)
        self.env.shell.setenv(env_var_name, secret_value, quiet=True)

    def _setenv_tmpfile_from_secret(self, env_var_name, secret_name, file_name):
        """get file contents from secretsmanager, store as file under /tmp, and store path in environment variable"""
        file_path = self._tmpfile_from_secret(secret_name, file_name)
        self.env.shell.setenv(env_var_name, file_path)

    def _try_setup_pkcs11(self):
        """Attempt to setup for PKCS#11 tests, but bail out if we can't get SoftHSM2 installed"""

        # currently, we only support PKCS#11 on unix
        if sys.platform == 'darwin' or sys.platform == 'win32':
            print(f"PKCS#11 on '{sys.platform}' is not currently supported. PKCS#11 tests are disabled")
            return
        # run on arm for Raspberry Pi
        elif 'linux' in sys.platform and os.uname()[4][:3] == 'arm':
            print(f"PKCS#11 on 'ARM' is not currently supported. PKCS#11 tests are disabled")
            return

        # try to install SoftHSM2, so we can run PKCS#11 tests
        try:
            softhsm2_install_action = Builder.InstallPackages(['softhsm'])
            softhsm2_install_action.run(self.env)
        except Exception:
            print("WARNING: SoftHSM2 could not be installed. PKCS#11 tests are disabled")
            return

        softhsm2_lib = self._find_softhsm2_lib()
        if softhsm2_lib is None:
            print("WARNING: libsofthsm2.so not found. PKCS#11 tests are disabled")
            return

        # put SoftHSM2 config file and token directory under the temp dir.
        softhsm2_dir = os.path.join(tempfile.gettempdir(), 'softhsm2')
        conf_path = os.path.join(softhsm2_dir, 'softhsm2.conf')
        token_dir = os.path.join(softhsm2_dir, 'tokens')
        if os.path.exists(token_dir):
            self.env.shell.rm(token_dir)
        self.env.shell.mkdir(token_dir)
        self.env.shell.setenv('SOFTHSM2_CONF', conf_path)
        pathlib.Path(conf_path).write_text(f"directories.tokendir = {token_dir}\n")

        # print SoftHSM2 version
        self._exec_softhsm2_util('--version')

        # create token
        token_label = 'my-token'
        pin = '0000'
        init_token_result = self._exec_softhsm2_util('--init-token', '--free', '--label', token_label,
                                                     '--pin', pin, '--so-pin', '0000')

        # figure out which slot the token ended up in.
        #
        # older versions of SoftHSM2 (ex: 2.1.0) make us pass --slot number to the --import command.
        # (newer versions let us pass --label name instead)
        #
        # to learn the slot of our new token examine the output of the --show-slots command.
        # we can't just examine the output of --init-token because some versions
        # of SoftHSM2 (ex: 2.2.0) reassign tokens to random slots without printing out where they went.
        token_slot = self._find_sofhsm2_token_slot()

        # add private key to token
        # key must be in PKCS#8 format
        # we have this stored in secretsmanager
        key_path = self._tmpfile_from_secret('unit-test/privatekey-p8', 'privatekey.p8.pem')
        key_label = 'my-key'
        self._exec_softhsm2_util('--import', key_path, '--slot', token_slot,
                                 '--label', key_label, '--id', 'BEEFCAFE', '--pin', pin)

        # set env vars for tests
        self.env.shell.setenv('AWS_TEST_PKCS11_LIB', softhsm2_lib)
        self.env.shell.setenv('AWS_TEST_PKCS11_PIN', pin)
        self.env.shell.setenv('AWS_TEST_PKCS11_TOKEN_LABEL', token_label)
        self.env.shell.setenv('AWS_TEST_PKCS11_KEY_LABEL', key_label)

    def _find_softhsm2_lib(self):
        """Return path to SoftHSM2 shared lib, or None if not found"""

        # note: not using `ldconfig --print-cache` to find it because
        # some installers put it in weird places where ldconfig doesn't look
        # (like in a subfolder under lib/)

        for lib_dir in ['lib64', 'lib']:  # search lib64 before lib
            for base_dir in ['/usr/local', '/usr', '/', ]:
                search_dir = os.path.join(base_dir, lib_dir)
                for root, dirs, files in os.walk(search_dir):
                    for file_name in files:
                        if 'libsofthsm2.so' in file_name:
                            return os.path.join(root, file_name)
        return None

    def _exec_softhsm2_util(self, *args, **kwargs):
        if 'check' not in kwargs:
            kwargs['check'] = True

        result = self.env.shell.exec('softhsm2-util', *args, **kwargs)

        # older versions of softhsm2-util (2.1.0 is a known offender)
        # return error code 0 and print the help if invalid args are passed.
        # This should be an error.
        #
        # invalid args can happen because newer versions of softhsm2-util
        # support more args than older versions, so what works on your
        # machine might not work on some ancient docker image.
        if 'Usage: softhsm2-util' in result.output:
            raise Exception('softhsm2-util failed')

        return result

    def _find_sofhsm2_token_slot(self):
        """Return slot ID of first initialized token"""

        output = self._exec_softhsm2_util('--show-slots').output

        # --- output looks like ---
        # Available slots:
        # Slot 0
        #    Slot info:
        #        ...
        #        Token present:    yes
        #    Token info:
        #        ...
        #        Initialized:      yes
        current_slot = None
        current_info_block = None
        for line in output.splitlines():
            # check for start of "Slot <ID>" block
            m = re.match(r"Slot ([0-9]+)", line)
            if m:
                current_slot = m.group(1)
                current_info_block = None
                continue

            if current_slot is None:
                continue

            # check for start of next indented block, like "Token info"
            m = re.match(r"    ([^ ].*)", line)
            if m:
                current_info_block = m.group(1)
                continue

            if current_info_block is None:
                continue

            # if we're in token block, check for "Initialized: yes"
            if "Token info" in current_info_block:
                if re.match(r" *Initialized: *yes", line):
                    return current_slot

        raise Exception('No initialized tokens found')



class AWSCrtPython(Builder.Action):
    python = PYTHON_DEFAULT

    # Some CI containers have pip installed via "rpm" or non-Python methods, and this causes issues when
    # we try to update pip via "python -m pip install --upgrade" because there are no RECORD files present.
    # Therefore, we have to seek alternative ways with a last resort of installing with "--ignore-installed"
    # if nothing else works AND the builder is running in GitHub actions.
    # As of writing, this is primarily an issue with the AL2-x64 image.
    def try_to_upgrade_pip(self, env):
        did_upgrade = False

        if (self.python == '{python}'):
            self.python = env.config["variables"]["python"]

        pip_result = env.shell.exec(self.python, '-m', 'pip', 'install', '--upgrade', 'pip', check=False)
        if pip_result.returncode == 0:
            did_upgrade = True
        else:
            print("Could not update pip via normal pip upgrade. Next trying via package manager...")

        if (did_upgrade == False):
            try:
                Builder.InstallPackages(['pip']).run(env)
                did_upgrade = True
            except Exception:
                print("Could not update pip via package manager. Next resorting to forcing an ignore install...")

        if (did_upgrade == False):
            # Only run in GitHub actions by checking for specific environment variable
            # Source: https://docs.github.com/en/actions/learn-github-actions/variables#default-environment-variables
            if (os.getenv("GITHUB_ACTIONS") is not None):
                pip_result = env.shell.exec(
                    self.python, '-m', 'pip', 'install', '--upgrade',
                    '--ignore-installed', 'pip', check=False)
                if pip_result.returncode == 0:
                    did_upgrade = True
                else:
                    print("Could not update pip via ignore install! Something is terribly wrong!")
                    sys.exit(12)
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
