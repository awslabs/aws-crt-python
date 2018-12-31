import setuptools
import os
import subprocess
from subprocess import CalledProcessError
import platform
from os import path
import sys
    
def is_64bit():
    if sys.maxsize > 2**32:
        return True

    return False

def is_32bit():
    return is_64bit() == False

def is_arm ():
    return platform.machine().startswith('arm')

def determine_cross_compile_string():
    host_arch = platform.machine()
    if (host_arch == 'AMD64' or host_arch == 'x86_64') and is_32bit() and sys.platform != 'win32':
        return 'CMAKE_C_FLAGS=-m32'
 
    return ''        
    
def determine_generator_string():
    if sys.platform == 'win32':
        vs_version = None

        if vs_version == None:
            if os.path.exists('C:\\Program Files (x86)\\Microsoft Visual Studio\\2019'):
                vs_version = '16.0'
                print('found installed version of Visual Studio 2019')
            elif os.path.exists('C:\\Program Files (x86)\\Microsoft Visual Studio\\2017'):
                vs_version = '15.0'
                print('found installed version of Visual Studio 2017')
            elif os.path.exists('C:\\Program Files (x86)\\Microsoft Visual Studio 14.0'):
                vs_version = '14.0'
                print('found installed version of Visual Studio 2015')
            else:
                print('Making an attempt at calling vswhere')
                vswhere_args = ['%ProgramFiles(x86)%\\Microsoft Visual Studio\\Installer\\vswhere.exe', '-legacy', '-latest', '-property', 'installationVersion']
                vswhere_output = None

                try:
                    vswhere_output = subprocess.check_output(vswhere_args, shell=True)
                except CalledProcessError as ex:
                    print('No version of MSVC compiler could be found!')
                    exit(1)       
 
                if vswhere_output != None:
                    for out in vswhere_output.split():
                        vs_version = out.decode('utf-8')
                        print('selected candidate {0}'.format(vs_version))
                        break 
                else:
                    print('No MSVC compiler could be found!')
                    exit(1)
        
        vs_major_version = vs_version.split('.')[0]

        cmake_list_gen_args = ['cmake', '--help']
        cmake_help_output = subprocess.check_output(cmake_list_gen_args)
        
        vs_version_gen_str = None
        for out in cmake_help_output.splitlines():
            trimmed_out = out.decode('utf-8').strip()
            if 'Visual Studio' in trimmed_out and vs_major_version in trimmed_out:
                print('Considering generator {}'.format(trimmed_out))
                vs_version_gen_str = trimmed_out.split('[')[0].strip()       
        
        if vs_version_gen_str == None:
            print('CMake does not recognize an installed version of visual studio on your system.')
            exit(1)
            
        if is_64bit():
            print('64bit version of python detected, using win64 builds')
            vs_version_gen_str = vs_version_gen_str + ' Win64'

        vs_version_gen_str = '-G' + vs_version_gen_str  
        print('Succesfully determined generator as \"{}\"'.format(vs_version_gen_str))      
        return vs_version_gen_str
    return ''    
    
generator_string = determine_generator_string()
cross_compile_string = determine_cross_compile_string()
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
common_cmake_args = ['cmake', generator_string, cross_compile_string, '-DVERSION_LIBS=OFF', '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=OFF', common_dir]
s2n_cmake_args = ['cmake', generator_string, cross_compile_string, '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=OFF', s2n_dir]
io_cmake_args = ['cmake', generator_string, cross_compile_string, '-DVERSION_LIBS=OFF', '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=OFF', io_dir]
mqtt_cmake_args = ['cmake', generator_string, cross_compile_string, '-DVERSION_LIBS=OFF', '-DCMAKE_INSTALL_PREFIX={}'.format(dep_install_path), '-DBUILD_SHARED_LIBS=OFF', mqtt_dir]
build_cmd = ['cmake', '--build', './', '--config', 'release', '--target', 'install']

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

if sys.platform != 'darwin' and sys.platform != 'win32': 
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

include_dirs = [path.join(dep_install_path, 'include')]
libraries = list(aws_c_libs)
library_dirs = [path.join(dep_install_path, 'lib')]
extra_objects = []

if compiler_type == 'msvc':
    pass
else:
    cflags += ['-O0', '-Wextra', '-Werror']

if sys.platform == 'win32':
    #the windows apis being used under the hood. Since we're static linking we have to follow the entire chain down
    libraries += ['Secur32', 'Crypt32', 'Advapi32', 'BCrypt', 'Kernel32', 'Ws2_32']
elif sys.platform == 'darwin':
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
        '{}/lib/lib{}.a'.format(dep_install_path, lib) for lib in aws_c_libs]
else:
    include_dirs = ['/usr/local/include'] + include_dirs
    library_dirs = ['/usr/local/lib'] + library_dirs
    libraries += ['s2n', 'crypto']
    aws_c_libs += ['s2n']
    try:
        cflags = [os.environ['CFLAGS']]
    except:
        pass
    try:
        ldflags = [os.environ['LDFLAGS']]
    except:
        pass

os.environ['CFLAGS'] = ' '.join(cflags)
os.environ['LDFLAGS'] = ' '.join(ldflags)

_aws_crt_python = setuptools.Extension(
    '_aws_crt_python',
    language = 'c',
    define_macros = [
        ('MAJOR_VERSION', '1'),
        ('MINOR_VERSION', '0'),
    ],
    include_dirs = ['/usr/local/include', dep_install_path + '/include'],
    library_dirs = ['/usr/local/lib', dep_install_path + '/lib'],
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
    author="Amazon Web Services, Inc",
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
        
