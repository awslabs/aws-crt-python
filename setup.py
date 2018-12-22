import setuptools
import os
import subprocess
from os import path
import sys

current_dir = os.path.dirname(os.path.realpath(__file__))

build_dir = os.path.join(current_dir, 'deps_build')

if not os.path.exists(build_dir):
    os.mkdir(build_dir)

os.chdir(build_dir)

dep_install_path = os.path.join(os.getcwd(), 'install')

if 'AWS_C_INSTALL' in os.environ:
    dep_install_path = os.getenv('AWS_C_INSTALL')

common_dir = os.path.join(current_dir, 'aws-c-common')
s2n_dir = os.path.join(current_dir, 's2n')
io_dir = os.path.join(current_dir, 'aws-c-io')
mqtt_dir = os.path.join(current_dir, 'aws-c-mqtt')
common_cmake_args = ['cmake', '-G', 'Ninja', '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=ON', common_dir]
s2n_cmake_args = ['cmake', '-G', 'Ninja', '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=ON', s2n_dir]
io_cmake_args = ['cmake', '-G', 'Ninja', '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=ON', io_dir]
mqtt_cmake_args = ['cmake', '-G', 'Ninja', '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=ON', mqtt_dir]
build_cmd = ['cmake', '--build', './', '--target', 'install']

common_build_dir = os.path.join(build_dir, 'aws-c-common')
s2n_build_dir = os.path.join(build_dir, 's2n')
io_build_dir = os.path.join(build_dir, 'aws-c-io')
mqtt_build_dir = os.path.join(build_dir, 'aws-c-mqtt')

if sys.platform.startswith('win'):
    shell = True
else:
    shell = False

if not os.path.exists(common_build_dir):
    os.mkdir(common_build_dir)
os.chdir(common_build_dir)

ret_code = subprocess.check_call(common_cmake_args, stderr=subprocess.STDOUT, shell=shell)
ret_code = subprocess.check_call(build_cmd, stderr=subprocess.STDOUT, shell=shell)

os.chdir(build_dir)

if not os.path.exists(s2n_build_dir):
    os.mkdir(s2n_build_dir)

os.chdir(s2n_build_dir)

if sys.platform != 'darwin' and sys.platform != 'windows': 
    ret_code = subprocess.check_call(s2n_cmake_args, stderr=subprocess.STDOUT, shell=shell)
    ret_code = subprocess.check_call(build_cmd, stderr=subprocess.STDOUT, shell=shell)

os.chdir(build_dir)

if not os.path.exists(io_build_dir):
    os.mkdir(io_build_dir)

os.chdir(io_build_dir)

ret_code = subprocess.check_call(io_cmake_args, stderr=subprocess.STDOUT, shell=shell)
ret_code = subprocess.check_call(build_cmd, stderr=subprocess.STDOUT, shell=shell)

os.chdir(build_dir)

if not os.path.exists(mqtt_build_dir):
    os.mkdir(mqtt_build_dir)

os.chdir(mqtt_build_dir)

ret_code = subprocess.check_call(mqtt_cmake_args, stderr=subprocess.STDOUT, shell=shell)
ret_code = subprocess.check_call(build_cmd, stderr=subprocess.STDOUT, shell=shell)
 
os.chdir(current_dir)

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
    libraries += ['s2n', 'crypto']
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
