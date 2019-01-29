Set-PSDebug -Trace 1
Start-Process "C:\\Python27\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python27\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python33\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python33\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python34\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python34\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program Files\\Python35\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program Files\\Python35\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program Files\\Python36\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program Files\\Python36\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program Files\\Python37\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program Files\\Python37\\pythonw.exe setup.py sdist bdist_wheel" -Wait

