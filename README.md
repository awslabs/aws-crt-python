## AWS Crt Python

Python bindings for the AWS Common Runtime

## License

This library is licensed under the Apache 2.0 License. 

## Building the Wheel

This builds the wheel itself
````bash
<path to your python binary> setup.py sdist bdist_wheel
````

You'll want to do this for every version of Python:
2.7m, 2.7mu, 3.4m, 3.5m, 3.6m, and 3.7m

Don't worry, it will only do a full build on the first run. All the others will just reuse the artifacts.

### Intel Linux
On linux, assuming you built on an ancient distro (GLIBC is <= 2.5), you'll need to have python inspect the artifact
and ensure it's compatible:

````bash
auditwheel show dist/<your output wheel>
````

If everything is good to go, you'll see a line that says:

following platform tag: "manylinux1_\<arch\>".

One thing to keep in mind, you'll need a version of libcrypto build as a static lib with position independent code (-fPIC).
DO NOT use the shared lib version of libcrypto or the wheel will not pass this test.

Now you'll need to have the wheel renamed to something compatible with pypi: 

````bash
auditwheel repair --plat manylinux1_x86_64 -w dist dist/<your image name>
````

After doing this, I like to delete all of the old wheel images for making the next step easier:

### ARM Linux
The process is similar to Intel, but we haven't built the wheels yet. We'll update this document when we finally get that finished.

## Publishing
Upload to pypi:

````bash
<path to your python binary> -m twine upload --repository-url <the repo> dist/*
````

## Using From Your Python Application

Normally, you just declare `aws_crt` as a dependency in your setup.py file.

### Installing from pip
````bash
pip install aws_crt
````
