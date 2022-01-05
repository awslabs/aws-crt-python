
import Builder
import argparse
import os.path
import pathlib
import subprocess
import re
import sys
import tempfile


class InstallPythonReqs(Builder.Action):
    def __init__(self, trust_hosts=False, deps=[], python=sys.executable):
        self.trust_hosts = trust_hosts
        self.core = ('pip', 'setuptools')
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


class SetupForTests(Builder.Action):

    def run(self, env):
        # we want to use boto3 to pull data from secretsmanager
        # boto3 might need to be installed first...
        try:
            import boto3
        except Exception:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'boto3'])
            import boto3

        self.env = env
        self.secrets = boto3.client('secretsmanager')

        self._setenv_from_secret('AWS_TEST_IOT_MQTT_ENDPOINT', 'unit-test/endpoint')

        self._setenv_tmpfile_from_secret('AWS_TEST_TLS_CERT_PATH', 'unit-test/certificate', 'certificate.pem')
        self._setenv_tmpfile_from_secret('AWS_TEST_TLS_KEY_PATH', 'unit-test/privatekey', 'privatekey.pem')

        # enable S3 tests
        env.shell.setenv('AWS_TEST_S3', '1')

        self._try_setup_pkcs11()

    def _try_setup_pkcs11(self):
        """Attempt to setup for PKCS#11 tests, but bail out if we can't get SoftHSM2 installed"""

        # currently, we only support PKCS#11 on unix
        if sys.platform == 'darwin' or sys.platform == 'win32':
            print(f"WARNING: PKCS#11 tests are disabled on this platform")
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
        # older versions of SoftHSM2 (2.1.0) make us pass --slot number to the --import command.
        # (newer version let us pass --label name instead)
        #
        # to learn the slot of our new token examine the output of the --show-slots command.
        # we can't just examine the output of --init-token because some versions
        # of SoftHSM2 (2.2.0) reassign tokens to random slots without printing out where they went.
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

    def _tmpfile_from_secret(self, secret_name, file_name):
        """get file contents from secretsmanager, store as file under /tmp, return file path"""
        response = self.secrets.get_secret_value(SecretId=secret_name)
        file_contents = response['SecretString']
        file_path = os.path.join(tempfile.gettempdir(), file_name)
        pathlib.Path(file_path).write_text(file_contents)
        return file_path

    def _setenv_from_secret(self, env_var_name, secret_name):
        """get string from secretsmanager and store in environment variable"""

        response = self.secrets.get_secret_value(SecretId=secret_name)
        self.env.shell.setenv(env_var_name, response['SecretString'])

    def _setenv_tmpfile_from_secret(self, env_var_name, secret_name, file_name):
        """get file contents from secretsmanager, store as file under /tmp, and store path in environment variable"""
        file_path = self._tmpfile_from_secret(secret_name, file_name)
        self.env.shell.setenv(env_var_name, file_path)

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

    def run(self, env):
        # allow custom python to be used
        parser = argparse.ArgumentParser()
        parser.add_argument('--python')
        args = parser.parse_known_args(env.args.args)[0]
        python = args.python if args.python else sys.executable

        actions = [
            InstallPythonReqs(deps=['boto3'], python=python),
            SetupForTests(),
            [python, '-m', 'pip', 'install', '--verbose', '.'],
            # "--failfast" because, given how our leak-detection in tests currently works,
            # once one test fails all the rest usually fail too.
            [python, '-m', 'unittest', 'discover', '--verbose', '--failfast'],
            # http_client_test.py launches external processes using the extra args
            [python, 'crt/aws-c-http/integration-testing/http_client_test.py',
                python, 'elasticurl.py'],
        ]

        return Builder.Script(actions, name='aws-crt-python')
