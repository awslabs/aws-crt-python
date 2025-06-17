
"C:\Program Files (x86)\Python39-32\python.exe" .\continuous-delivery\update-version.py || goto error

"C:\Program Files (x86)\Python38-32\python.exe" -m build || goto error
"C:\Program Files (x86)\Python39-32\python.exe" -m build || goto error
"C:\Program Files (x86)\Python310-32\python.exe" -m build || goto error
"C:\Program Files (x86)\Python311-32\python.exe" -m build || goto error

:: Don't need to build wheels for Python 3.12, it works with the 3.11 stable ABI wheel

:: We are using the 3.13 stable ABI from 3.13 onwards because of deprecated functions.
"C:\Program Files (x86)\Python313-32\python.exe" -m build || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
