@echo on

@"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
echo "Installing python version: %* via choco"
choco install %* -y --no-progress || goto error
call RefreshEnv.cmd

git submodule update --init --recursive || goto error
mkdir build\deps\install
set AWS_C_INSTALL=%cd%\build\deps\install

echo --- installing crt ---
python setup.py build install || goto error

echo --- unittest ---
python -u -v -m unittest discover --verbose || goto error

echo --- elasticurl GET ---
python elasticurl.py -v ERROR -i https://example.com || goto error

echo --- elasticurl PUT ---
python elasticurl.py -v ERROR -P -H "content-type: application/json" -i -d "{'test':'testval'}" http://httpbin.org/post || goto error

echo --- common-windows.bat SUCCESS ---
goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
