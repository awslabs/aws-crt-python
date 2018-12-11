import setuptools
import os
from os import path
import sys

from distutils.ccompiler import get_default_compiler
compiler_type = get_default_compiler()

aws_c_libs = ['aws-c-mqtt', 'aws-c-io', 'aws-c-common']

cflags = []
ldflags = []

include_dirs = [path.join(os.getenv('AWS_C_INSTALL'), 'include')]
libraries = aws_c_libs
library_dirs = [path.join(os.getenv('AWS_C_INSTALL'), 'lib')]
extra_objects = []

if compiler_type == 'msvc':
    pass
else:
    cflags += ['-O0', '-Wextra', '-Werror']

if sys.platform == 'linux':
    include_dirs = ['/usr/local/include'] + include_dirs
    library_dirs = ['/usr/local/lib'] + library_dirs
    try:
        cflags = [os.environ['CFLAGS']]
    except:
        pass
    try:
        ldflags = [os.environ['LDFLAGS']]
    except:
        pass

if sys.platform == 'darwin':
    try:
        cflags = [os.environ['CFLAGS']]
    except:
        pass
    try:
        ldflags = [os.environ['LDFLAGS']]
    except:
        pass
    ldflags += ['-framework Security']
    include_dirs = ['/usr/local/include'] + include_dirs
    library_dirs = ['/usr/local/lib'] + library_dirs
    extra_objects = [
        '{}/lib/lib{}.a'.format(os.getenv('AWS_C_INSTALL'), lib) for lib in aws_c_libs]
    libraries = []

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
    libraries = libraries,
    sources = [
        'source/module.c',
        'source/io.c',
        'source/mqtt_client.c',
        'source/mqtt_client_connection.c',
    ],
    extra_objects = extra_objects
)

setuptools.setup(
    name="aws_crt",
    version="0.0.1",
    author="Example Author",
    author_email="author@example.com",
    description="A common runtime for AWS Python projects",
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
