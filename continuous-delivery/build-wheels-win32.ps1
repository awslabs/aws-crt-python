Set-PSDebug -Trace 1
Start-Process "C:\\Python27\ (x86)\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python27\ (x86)\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python33\ (x86)\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python33\ (x86)\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python34\ (x86)\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Python34\ (x86)\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program\ Files\ (x86)\\Python35\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program\ Files\ (x86)\\Python35\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program\ Files\ (x86)\\Python36\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program\ Files\ (x86)\\Python36\\pythonw.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program\ Files\ (x86)\\Python37\\python.exe setup.py sdist bdist_wheel" -Wait
Start-Process "C:\\Program\ Files\ (x86)\\Python37\\pythonw.exe setup.py sdist bdist_wheel" -Wait

