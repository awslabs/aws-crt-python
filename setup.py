# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

import distutils.ccompiler
import glob
import os
import os.path
import platform
import setuptools
import setuptools.command.build_ext
import subprocess
import sys

# TODO: IS it possible to build debug? what does --debug do?
# TODO: any other cmdline things I should be passing along?
# TODO: is the lib name stuff really doing anything?
# TODO: parallel?


def is_64bit():
    return sys.maxsize > 2**32


def is_32bit():
    return is_64bit() == False


def is_arm():
    return platform.machine().startswith('arm')


def determine_cross_compile_string():
    host_arch = platform.machine()
    if (host_arch == 'AMD64' or host_arch == 'x86_64') and is_32bit() and sys.platform != 'win32':
        return '-DCMAKE_C_FLAGS=-m32'
    return ''


def determine_generator_string():
    if sys.platform == 'win32':
        prog_x86_path = os.getenv('PROGRAMFILES(x86)')
        if os.path.exists(prog_x86_path + '\\Microsoft Visual Studio\\2019'):
            vs_version = '16.0'
            print('found installed version of Visual Studio 2019')
        elif os.path.exists(prog_x86_path + '\\Microsoft Visual Studio\\2017'):
            vs_version = '15.0'
            print('found installed version of Visual Studio 2017')
        elif os.path.exists(prog_x86_path + '\\Microsoft Visual Studio 14.0'):
            vs_version = '14.0'
            print('found installed version of Visual Studio 2015')
        else:
            print('Making an attempt at calling vswhere')
            vswhere_args = [
                '%ProgramFiles(x86)%\\Microsoft Visual Studio\\Installer\\vswhere.exe',
                '-legacy',
                '-latest',
                '-property',
                'installationVersion']
            vswhere_output = None

            try:
                vswhere_output = subprocess.check_output(vswhere_args, shell=True)
            except subprocess.CalledProcessError:
                raise RuntimeError('No version of MSVC compiler could be found!')

            if vswhere_output is not None:
                for out in vswhere_output.split():
                    vs_version = out.decode('utf-8')
            else:
                raise RuntimeError('No MSVC compiler could be found!')

        vs_major_version = vs_version.split('.')[0]

        cmake_list_gen_args = ['cmake', '--help']
        cmake_help_output = subprocess.check_output(cmake_list_gen_args)

        vs_version_gen_str = None
        for out in cmake_help_output.splitlines():
            trimmed_out = out.decode('utf-8').strip()
            if 'Visual Studio' in trimmed_out and vs_major_version in trimmed_out:
                print('selecting generator {}'.format(trimmed_out))
                vs_version_gen_str = trimmed_out.split('[')[0].strip(' *')
                break

        if vs_version_gen_str is None:
            raise RuntimeError('CMake does not recognize an installed version of visual studio on your system.')

        if is_64bit():
            print('64bit version of python detected, using win64 builds')
            vs_version_gen_str = vs_version_gen_str + ' Win64'

        vs_version_gen_str = '-G' + vs_version_gen_str
        print('Succesfully determined generator as \"{}\"'.format(vs_version_gen_str))
        return vs_version_gen_str
    return ''


class AwsLib(object):
    def __init__(self, name, extra_cmake_args=[]):
        self.name = name
        self.extra_cmake_args = extra_cmake_args


# The extension depends on these libs.
# They're built along with the extension, in the order listed.
aws_libs = []
if sys.platform != 'darwin' and sys.platform != 'win32':
    aws_libs.append(AwsLib('s2n', extra_cmake_args=['-DUSE_S2N_PQ_CRYPTO=OFF']))
aws_libs.append(AwsLib('aws-c-common'))
aws_libs.append(AwsLib('aws-c-io'))
aws_libs.append(AwsLib('aws-c-cal'))
aws_libs.append(AwsLib('aws-c-compression'))
aws_libs.append(AwsLib('aws-c-http'))
aws_libs.append(AwsLib('aws-c-mqtt'))


class awscrt_build_ext(setuptools.command.build_ext.build_ext):
    def _build_dependency(self, aws_lib):
        prev_cwd = os.getcwd()  # restore cwd at end of function
        lib_source_dir = os.path.join(self.current_dir, aws_lib.name)

        # Skip library if it wasn't pulled
        if not os.path.exists(os.path.join(lib_source_dir, 'CMakeLists.txt')):
            print("--- Skipping dependency: '{}' source not found ---".format(aws_lib.name))
            return

        print("--- Building dependency: {} ---".format(aws_lib.name))
        lib_build_dir = os.path.join(self.dep_build_dir, aws_lib.name)
        if not os.path.exists(lib_build_dir):
            os.makedirs(lib_build_dir)

        os.chdir(lib_build_dir)

        build_type = 'Debug' if self.debug else 'Release'

        # cmake configure
        cmake_args = [
            'cmake',
            determine_generator_string(),
            determine_cross_compile_string(),
            '-DCMAKE_PREFIX_PATH={}'.format(self.dep_install_path),
            '-DCMAKE_INSTALL_PREFIX={}'.format(self.dep_install_path),
            '-DBUILD_SHARED_LIBS=OFF',
            '-DCMAKE_BUILD_TYPE={}'.format(build_type),
            '-DBUILD_TESTING=OFF',
        ]
        if self.include_dirs:
            cmake_args.append('-DCMAKE_INCLUDE_PATH={}'.format(';'.join(self.include_dirs)))
        if self.library_dirs:
            cmake_args.append('-DCMAKE_LIBRARY_PATH={}'.format(';'.join(self.library_dirs)))
        cmake_args.extend(aws_lib.extra_cmake_args)
        cmake_args.append(lib_source_dir)

        subprocess.check_call(cmake_args)

        # cmake build/install
        build_cmd = [
            'cmake',
            '--build', './',
            '--config', build_type,
            '--target', 'install',
        ]
        subprocess.check_call(build_cmd)

        os.chdir(prev_cwd)

    def run(self):
        # build dependencies
        self.current_dir = os.path.dirname(os.path.realpath(__file__))
        self.dep_build_dir = os.path.join(self.current_dir, self.build_temp, 'deps')
        self.dep_install_path = os.environ.get('AWS_C_INSTALL', os.path.join(self.dep_build_dir, 'install'))

        for lib in aws_libs:
            self._build_dependency(lib)

        # update paths so awscrt_ext can access dependencies
        self.include_dirs.append(os.path.join(self.dep_install_path, 'include'))

        lib_dir = 'lib'
        if is_64bit() and os.path.exists(os.path.join(self.dep_install_path, 'lib64')):
            lib_dir = 'lib64'
        if is_32bit() and os.path.exists(os.path.join(self.dep_install_path, 'lib32')):
            lib_dir = 'lib32'

        self.library_dirs.append(os.path.join(self.dep_install_path, lib_dir))

        # continue with normal build_ext.run()
        super(setuptools.command.build_ext.build_ext, self).run()


def awscrt_ext():
    # fetch the CFLAGS/LDFLAGS from env
    extra_compile_args = os.environ.get('CFLAGS', '').split()
    extra_link_args = os.environ.get('LDFLAGS', '').split()

    libraries = [x.name for x in aws_libs]

    # libraries must be passed to the linker with upstream dependencies listed last.
    libraries.reverse()

    if sys.platform == 'win32':
        # the windows apis being used under the hood. Since we're static linking we have to follow the entire chain down
        libraries += ['Secur32', 'Crypt32', 'Advapi32', 'BCrypt', 'Kernel32', 'Ws2_32', 'Shlwapi']
    else:
        if sys.platform == 'darwin':
            extra_link_args += ['-framework', 'Security']
        else:
            libraries += ['crypto', 'rt']

    if distutils.ccompiler.get_default_compiler() != 'msvc':
        extra_compile_args += ['-Wextra', '-Werror', '-Wno-strict-aliasing', '-std=gnu99']

    return setuptools.Extension(
        '_awscrt',
        language='c',
        libraries=libraries,
        sources=glob.glob('source/*.c'),
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    )


setuptools.setup(
    name="awscrt",
    version="0.2.26",
    author="Amazon Web Services, Inc",
    author_email="aws-sdk-common-runtime@amazon.com",
    description="A common runtime for AWS Python projects",
    url="https://github.com/awslabs/aws-crt-python",
    packages=['awscrt'],
    classifiers=[
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'enum34;python_version<"3.4"',
        'futures;python_version<"3.2"',
    ],
    ext_modules=[awscrt_ext()],
    cmdclass={'build_ext': awscrt_build_ext},
    test_suite='test',
)
