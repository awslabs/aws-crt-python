
"C:\Program Files (x86)\Python39-32\python.exe" .\continuous-delivery\update-version.py || goto error

"C:\Program Files (x86)\Python36-32\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files (x86)\Python37-32\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files (x86)\Python38-32\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files (x86)\Python39-32\python.exe" setup.py sdist bdist_wheel || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
