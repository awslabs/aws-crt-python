

@"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -InputFormat None -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
echo "Installing python version: %* via choco"
choco install %* -y
call RefreshEnv.cmd

git submodule update --init --recursive
mkdir build\deps\install
set AWS_C_INSTALL=%cd%\build\deps\install

python setup.py build install
python elasticurl.py -v ERROR -P -H "content-type: application/json" -i -d "{'test':'testval'}" http://httpbin.org/post
python elasticurl.py -v ERROR -i https://example.com
python -m unittest

exit /b %errorlevel%
