import setuptools
import os
import sys

from distutils.ccompiler import get_default_compiler
compiler_type = get_default_compiler()

cflags = []
ldflags = []

if compiler_type == 'msvc':
    pass
else:
    cflags += ['-O0', '-fsanitize=address']

if sys.platform == 'darwin':
    ldflags += ['-framework Security']

os.environ['CFLAGS'] = ' '.join(cflags)
os.environ['LDFLAGS'] = ' '.join(ldflags)

_aws_crt_python = setuptools.Extension(
    '_aws_crt_python',
    language = 'c',
    define_macros = [
        ('MAJOR_VERSION', '1'),
        ('MINOR_VERSION', '0'),
    ],
    include_dirs = ['/usr/local/include', os.getenv('AWS_C_INSTALL') + '/include'],
    library_dirs = ['/usr/local/lib', os.getenv('AWS_C_INSTALL') + '/lib'],
    libraries = ['aws-c-common', 'aws-c-io', 'aws-c-mqtt'],
    sources = [
        'source/module.c',
        'source/io.c',
        'source/mqtt_client_connection.c',
    ],
)

setuptools.setup(
    name="aws_crt",
    version="0.0.1",
    author="Example Author",
    author_email="author@example.com",
    description="A common runtime for AWS Python projects",
    long_description_content_type="text/markdown",
    url="https://github.com/awslabs/aws-crt-python",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    ext_modules = [_aws_crt_python],
)
