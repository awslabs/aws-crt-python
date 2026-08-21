@echo off

if not defined PYTHON311_ARM64 goto missing_python
if not defined PYTHON313_ARM64 goto missing_python
if not defined PYTHON313T_ARM64 goto missing_python
if not defined PYTHON314T_ARM64 goto missing_python

"%PYTHON311_ARM64%" -c "import sys, sysconfig; raise SystemExit(0 if sys.version_info[:2] == (3, 11) and sysconfig.get_platform() == 'win-arm64' and not sysconfig.get_config_var('Py_GIL_DISABLED') else 1)" || goto wrong_python
"%PYTHON313_ARM64%" -c "import sys, sysconfig; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and sysconfig.get_platform() == 'win-arm64' and not sysconfig.get_config_var('Py_GIL_DISABLED') else 1)" || goto wrong_python
"%PYTHON313T_ARM64%" -c "import sys, sysconfig; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and sysconfig.get_platform() == 'win-arm64' and sysconfig.get_config_var('Py_GIL_DISABLED') else 1)" || goto wrong_python
"%PYTHON314T_ARM64%" -c "import sys, sysconfig; raise SystemExit(0 if sys.version_info[:2] == (3, 14) and sysconfig.get_platform() == 'win-arm64' and sysconfig.get_config_var('Py_GIL_DISABLED') else 1)" || goto wrong_python

"%PYTHON313_ARM64%" continuous-delivery\update-version.py || goto error

:: The 3.11 stable ABI wheel also supports Python 3.12.
"%PYTHON311_ARM64%" -m build || goto error

:: Use the 3.13 stable ABI from 3.13 onwards because of deprecated functions.
"%PYTHON313_ARM64%" -m build || goto error

:: Free-threaded builds do not support the Limited C API or stable ABI.
"%PYTHON313T_ARM64%" -m build || goto error
"%PYTHON314T_ARM64%" -m build || goto error

goto :EOF

:missing_python
echo PYTHON311_ARM64, PYTHON313_ARM64, PYTHON313T_ARM64, and PYTHON314T_ARM64 must point to native ARM64 Python executables.
exit /b 1

:wrong_python
echo Configured Python executables must have the expected version, win-arm64 platform, and free-threaded status.
exit /b 1

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%