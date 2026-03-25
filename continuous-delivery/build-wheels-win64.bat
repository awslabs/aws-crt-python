"C:\Program Files\Python39\python.exe" continuous-delivery\update-version.py || goto error

"C:\Program Files\Python38\python.exe" -m build || goto error
"C:\Program Files\Python39\python.exe" -m build || goto error
"C:\Program Files\Python310\python.exe" -m build || goto error
"C:\Program Files\Python311\python.exe" -m build || goto error

:: Don't need to build wheels for Python 3.12, it works with the 3.11 stable ABI wheel

:: We are using the 3.13 stable ABI from 3.13 onwards because of deprecated functions.
"C:\Program Files\Python313\python.exe" -m build || goto error

:: The free-threaded build does not currently support the Limited C API or the stable ABI. Built them separately
"C:\Program Files\Python-313\python3.13t.exe" -m build || goto error
"C:\Program Files\Python314\python3.14t.exe" -m build || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
