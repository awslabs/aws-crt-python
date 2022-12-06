# Development guide for aws-crt-python

This guide is for contributors to aws-crt-python's source code.
Familiarity (but not necessarily expertise) with Python and C is assumed.
This document covers basic setup and workflow.

For more advanced topics, see [writing-code.md](writing-code.md).

### Table of Contents

*   [Git](#git)
*   [CMake](#cmake)
*   [Set up a Virtual Environment](#set-up-a-virtual-environment)
*   [Install](#install)
*   [Run Tests](#run-tests)
    *   [Environment Variables for Tests](#environment-variables-for-tests)
*   [Using an IDE](#using-an-ide)
    *   [Visual Studio Code](#using-visual-studio-code-vscode)
        *   [Debugging Python](#debugging-python-with-vscode)
        *   [Debugging C](#debugging-c-with-vscode)

## Git

Clone to a development folder:
```sh
$ git clone git@github.com:awslabs/aws-crt-python.git
$ cd aws-crt-python
$ git submodule update --init
```

Note that you MUST manually update submodules any time you pull latest, or change branches:
```sh
$ git submodule update
```

## CMake

CMake 3 is required to compile the C submodules. To install:

*   On Mac, using homebrew:
    ```sh
    $ brew install cmake
    ```
* On Linux: use your system's package manager (apt, yum, etc).
* On Windows: [download and install](https://cmake.org/download/)

## Install Python Dev Libraries and Header files

Install the libraries and headers necessary for Python development.
These might already be installed. If you're not sure just skip ahead, and come back
to this step if you get build errors like: `Python.h: No such file or directory`

If you installed Python via [python.org](https://www.python.org/downloads/),
then you already have these files.

If you installed Python via a package manager, you might need the "dev" package.
i.e. `sudo apt install python3-dev` or `sudo yum install python3-devel`

## Set up a Virtual Environment

Set up a [virtual environment](https://docs.python.org/3/library/venv.html)
for development. This guide suggests `aws-crt-python/.venv/` as a default location.
Create a virtual environment like so:
```sh
$ python3 -m venv .venv/
```

To activate the virtual environment in your current terminal:
*   On Mac or Linux:
    ```sh
    $ source .venv/bin/activate
    ```
*   In Windows PowerShell:
    ```pwsh
    > .venv\Scripts\Activate.ps1
    ```
*   In Windows Command Prompt:
    ```bat
    > .venv\Scripts\Activate.bat
    ```

Your terminal looks something like this when the virtual environment is active:
```
(.venv) $
```
Now any time you type `python3` or `pip` or even `python`, you are using the
one from your virtual environment.
To stop using the virtual environment, run `deactivate`.

## Install

Install dev dependencies:
```sh
(.venv) $ python3 -m pip install --upgrade --requirement requirements-dev.txt
```

Install aws-crt-python (helper script `python3 scripts/install-dev.py` does this):
```sh
(.venv) $ python3 -m pip install --verbose --editable .
```

You must re-run this command any time the C source code changes.
But you don't need to re-run it if .py files change
(thanks to the `--editable` aka "develop mode" flag)

Note that this takes about twice as long on Mac, which compiles C for both `x86_64` and `arm64`.
(TODO: in develop mode, for productivity's sake, only compile C for one architecture,
and ignore resulting warnings from the linker)

## Run Tests

To run all tests:
```sh
(.venv) $ python3 -m unittest discover --failfast --verbose
```

`discover` automatically finds all tests to run

`--failfast` stops after one failed test.
This is useful because a failed test is likely to leak memory,
which will cause the rest of the tests to fail as well.

`--verbose` makes it easier to see which tests are skipped.

To run specific tests, specify a path. For example:
```sh
(.venv) $ python3 -m unittest --failfast --verbose test.test_http_client.TestClient.test_connect_http
```

More path examples:
*   `test` - everything under `test/` folder
*   `test.test_http_client` - every test in `test_http_client.py`
*   `test.test_http_client.TestClient` - every test in `TestClient` class
*   `test.test_http_client.TestClient.test_connect_http` - A single test

When creating new tests, note that the names of test files and test functions must be prefixed with `test_`.

### Environment Variables for Tests
Many tests require an AWS account. These tests are skipped unless
specific environment variables are set:

*   MQTT Tests
    *   `AWS_TEST_IOT_MQTT_ENDPOINT` - AWS IoT Core endpoint. This is specific to your account.
    *   `AWS_TEST_TLS_CERT_PATH` - file path to the certificate used to initialize the TLS context of the MQTT connection
    *   `AWS_TEST_TLS_KEY_PATH` - file path to the private key used to initialize the TLS context of the MQTT connection
    *   `AWS_TEST_TLS_ROOT_CERT_PATH` - file path to the root CA used to initialize the TLS context of the MQTT connection
*   PKCS#11 Tests
    *   `AWS_TEST_PKCS11_LIB` - path to PKCS#11 library
    *   `AWS_TEST_PKCS11_PIN` - user PIN for logging into PKCS#11 token
    *   `AWS_TEST_PKCS11_TOKEN_LABEL` - label of PKCS#11 token
    *   `AWS_TEST_PKCS11_KEY_LABEL` - label of private key on PKCS#11 token, which must correspond to the cert at `AWS_TEST_TLS_CERT_PATH`.
*   Proxy Tests
    * TLS-protected connections to the proxy
        *   `AWS_TEST_HTTPS_PROXY_HOST` - proxy host address
        *   `AWS_TEST_HTTPS_PROXY_PORT` - proxy port
    * Open connections to the proxy
        *   `AWS_TEST_HTTP_PROXY_HOST` - proxy host address
        *   `AWS_TEST_HTTP_PROXY_PORT` - port port
    * Open connections to the proxy, with basic authentication
        *   `AWS_TEST_HTTP_PROXY_BASIC_HOST` - proxy host address
        *   `AWS_TEST_HTTP_PROXY_BASIC_PORT` - proxy port
        *   `AWS_TEST_BASIC_AUTH_USERNAME` - username
        *   `AWS_TEST_BASIC_AUTH_PASSWORD` - password
*   S3 Tests
    *   `AWS_TEST_S3` - set to any value to enable S3 tests.
        *   **Unfortunately, at this time these tests can only be run by members of the
            Common Runtime team, due to hardcoded paths.**
        *   TODO: alter tests so anyone can run them.

## Code Formatting

We use automatic code formatters in this project and pull requests will fail unless
the code is formatted correctly.

`autopep8` is used for python code. You installed this earlier via `requirements-dev.txt`.

For C code `clang-format` is used (specifically version 9).
To install this on Mac using homebrew, run:
```sh
(.venv) $ brew install llvm@9
```

Use helper scripts to automatically format your code (or configure your IDE to do it):
```sh
# format all code
(.venv) $ python3 scripts/format-all.py

# just format Python files
(.venv) $ python3 scripts/format-python.py

# just format C files
(.venv) $ python3 scripts/format-c.py
```

## Using an IDE
### Using Visual Studio Code (VSCode)

1)  Install the following extensions:
    *   Python (Microsoft)
    *   C/C++ (Microsoft)
    *   Code Spell Checker (Street Side Software) - optional

2)  Open the `aws-crt-python/` folder.

3)  Use your virtual environment: `cmd+shift+p -> Python: Select Interpreter`

4)  Edit workspace settings: `cmd+shift+P -> Preferences: Open Workspace Settings`
    *   `Python > Terminal: Activate Env In Current Terminal` - ("python.terminal.activateEnvInCurrentTerminal" in json view)
        *   Set to true, so the VSCode terminal will always use your virtual environment.
        *   But your current terminal isn't using it. Kill the current terminal or reload the window to resolve this.
    *   `C_Cpp > Default: Include Path` - ("C_Cpp.default.includePath" in json view)
        *   Add item - set path to Python's C headers.
            For example: `/Library/Frameworks/Python.framework/Versions/3.10/include/python3.10`
        *   This is optional, it helps IntelliSense when viewing C files.
    *   `Files: Insert Final Newline` - ("files.insertFinalNewline" in json view)
        *   Set to true. It's just good practice.
    *   `Files: Trim Trailing Whitespace` - ("files.trimTrailingWhitespace" in json view)
        *   Set to true. It's just good practice.

5)  Add helpful tasks you can run via `cmd+shift+P -> Tasks: Run Task`
    *   Copy [this file](vscode/tasks.json) to `aws-crt-python/.vscode/tasks.json` for the following tasks:
        * `install` - `pip install` in develop mode. `cmd+shift+B` is a special shortcut for this task
        * `format` - format all code files

#### Debugging Python with VSCode
The VSCode `Testing` tab (lab flask/beaker icon) helps run and debug Python tests.
From this tab, click Configure Python Tests:
*   Select a test framework/tool to enable - unittest
*   Select the directory containing the tests - test
*   Select the pattern to identify test files - test_*.py

Run tests by mousing over the name and clicking the PLAY button,
or use the DEBUG button to hit breakpoints in Python code, and see output in the DEBUG CONSOLE.

Note that many tests are skipped unless [specific environment variables](#environment-variables-for-tests) are set.
You can set these in a `aws-crt-python/.env` file (don't worry it's ignored by git. For example:
```
AWS_TEST_IOT_MQTT_ENDPOINT=xxxxxxxxx-ats.iot.xxxxx.amazonaws.com
AWS_TEST_TLS_CERT_PATH=/Users/janedoe/iot/xxxxx-certificate.pem.crt
AWS_TEST_TLS_KEY_PATH=/Users/janedoe/iot/xxxxx-private.pem.key
```

#### Debugging C with VSCode
Unfortunately, we haven't figured out how to do interactive debugging of the C code.
Python ultimately builds and links the C module together, and it seems to always strip out the debug info.
Please update this guide if you know how. For now, `printf()` is your best option.

If you suspect the bug is in the external C code (i.e. [aws-c-http](https://github.com/awslabs/aws-c-http))
and need to do interactive debugging, your best bet is cloning that external project,
build it in Debug, and step through its tests.

# TODO
*   more about git submodules (latest-submodules.py and working from branches)
*   more about logging. consider easy way to turn on logging in tests

