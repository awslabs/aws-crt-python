FOR /F "delims=" %%A in ('git describe --tags') do ( set TAG_VERSION=%%A )
set CURRENT_VERSION=%TAG_VERSION:v=%

"C:\Program Files\Python38\python.exe" continuous-delivery\pip-install-with-retry.py --no-cache-dir -i https://testpypi.python.org/simple --user awscrt==%CURRENT_VERSION% || goto error
"C:\Program Files\Python38\python.exe" continuous-delivery\test-pip-install.py || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%

