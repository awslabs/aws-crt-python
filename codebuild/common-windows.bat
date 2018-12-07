cd ../
set CMAKE_ARGS=%*

mkdir install
set AWS_C_INSTALL=%cd%\\install

CALL :install_library aws-c-common
CALL :install_library aws-c-io
CALL :install_library aws-c-mqtt transactional-tree

cd aws-crt-python
mkdir build
cd build
cmake %CMAKE_ARGS% -DCMAKE_BUILD_TYPE="Release" -DCMAKE_INSTALL_PREFIX=%AWS_C_INSTALL% ../ || goto error
cmake --build . --config Release || goto error
ctest -V || goto error

goto :EOF

:install_library
git clone https://github.com/awslabs/%~1.git
cd %~1

if [%~2] == [] GOTO do_build
git checkout %~2

:do_build
python3 setup.py build
exit /b %errorlevel%

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
