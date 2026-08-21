@echo off

if not defined PYTHON311_ARM64 goto missing_python
if not defined PYTHON313_ARM64 goto missing_python
if not defined PYTHON313T_ARM64 goto missing_python
if not defined PYTHON314T_ARM64 goto missing_python

for %%P in ("%PYTHON311_ARM64%" "%PYTHON313_ARM64%" "%PYTHON313T_ARM64%" "%PYTHON314T_ARM64%") do (
	"%%~P" -c "import sysconfig; raise SystemExit(0 if sysconfig.get_platform() == 'win-arm64' else 1)" || goto wrong_architecture
)

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

:wrong_architecture
echo All configured Python executables must target win-arm64.
exit /b 1

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%