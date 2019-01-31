"C:\Python27 (x86)\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files (x86)\Python35-32\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files (x86)\Python36-32\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files (x86)\Python37-32\python.exe" setup.py sdist bdist_wheel || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%

