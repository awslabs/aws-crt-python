
set CMAKE_ARGS=%*

@"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
choco install %PYTHON_PACKAGE% -y
call RefreshEnv.cmd

mkdir build\deps\install
set AWS_C_INSTALL=%cd%\build\deps\install

CALL :install_library aws-c-common
CALL :install_library aws-c-io
CALL :install_library aws-c-mqtt

python3 setup.py build

goto :EOF

:install_library
pushd build\deps
git clone https://github.com/awslabs/%~1.git
cd %~1

if [%~2] == [] GOTO do_build
git checkout %~2

:do_build
cmake %CMAKE_ARGS% -DCMAKE_BUILD_TYPE="Release" -DCMAKE_INSTALL_PREFIX=%AWS_C_INSTALL% ../ || goto error
cmake --build . --config Release || goto error
cmake --build . --target INSTALL || goto error
popd
exit /b %errorlevel%

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
