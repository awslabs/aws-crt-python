"C:\Program Files\Python39\python.exe" continuous-delivery\update-version.py || goto error

"C:\Program Files\Python37\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python38\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python39\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python310\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python311\python.exe" setup.py sdist bdist_wheel || goto error

:: Don't need to build wheels for Python 3.12 and later.
:: The 3.11 wheel uses the stable ABI, so it works with newer versions too.

:: We are using the 3.13 stable ABI from 3.13 onwards because of deprecated functions.
"C:\Program Files\Python313\python.exe" setup.py sdist bdist_wheel || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
