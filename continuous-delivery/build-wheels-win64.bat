"C:\Program Files\Python38\python.exe" continuous-delivery\update-version.py || goto error

"C:\Python27\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python35\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python36\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python37\python.exe" setup.py sdist bdist_wheel || goto error
"C:\Program Files\Python38\python.exe" setup.py sdist bdist_wheel || goto error

goto :EOF

:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%

