FOR /F "delims=" %%A in ('git describe --abbrev^=0') do ( set CURRENT_VERSION=%%A )

"C:\Program Files\Python37\python.exe" -m pip install -i https://testpypi.python.org/simple --user awscrt==%CURRENT_VERSION% || goto error
"C:\Program Files\Python37\python.exe" continuous-delivery\test-pip-install.py || goto error

"C:\Python27\python.exe" -m pip install -i https://testpypi.python.org/simple --user awscrt==%CURRENT_VERSION% || goto error
"C:\Python27\python.exe" continuous-delivery\test-pip-install.py || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%

