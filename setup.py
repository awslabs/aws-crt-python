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

from __future__ import print_function
import distutils.ccompiler
import glob
import os
import os.path
import platform
import setuptools
import setuptools.command.build_ext
import subprocess
import sys


def is_64bit():
    return sys.maxsize > 2**32


def is_32bit():
    return is_64bit() == False


def is_arm():
    return platform.machine().startswith('arm')


def determine_cross_compile_args():
    host_arch = platform.machine()
    if (host_arch == 'AMD64' or host_arch == 'x86_64') and is_32bit() and sys.platform != 'win32':
        return ['-DCMAKE_C_FLAGS=-m32']
    return []


def determine_generator_args():
    if sys.platform == 'win32':
        try:
            # See which compiler python picks
            compiler = distutils.ccompiler.new_compiler()
            compiler.initialize()

            # Look at compiler path to divine the Visual Studio version.
            # This technique may not work with customized VS install paths.
            # An alternative would be to utilize private python calls:
            # (distutils._msvccompiler._find_vc2017() and _find_vc2015()).
            if '\\Microsoft Visual Studio\\2019' in compiler.cc:
                vs_version = 16
                vs_year = 2019
            elif '\\Microsoft Visual Studio\\2017' in compiler.cc:
                vs_version = 15
                vs_year = 2017
            elif '\\Microsoft Visual Studio 14.0' in compiler.cc:
                vs_version = 14
                vs_year = 2015
            assert(vs_version and vs_year)
        except BaseException:
            raise RuntimeError('No supported version of MSVC compiler could be found!')

        print('Using Visual Studio', vs_version, vs_year)

        vs_version_gen_str = "Visual Studio {} {}".format(vs_version, vs_year)

        if vs_year <= 2017:
            # For VS2017 and earlier, architecture goes at end of generator string
            if is_64bit():
                vs_version_gen_str += " Win64"
            return ['-G', vs_version_gen_str]

        # For VS2019 (and presumably later), architecture is passed via -A flag
        arch_str = "x64" if is_64bit() else "Win32"
        return ['-G', vs_version_gen_str, '-A', arch_str]

    return []


cmake_found = False


def check_cmake_installed():
    global cmake_found
    if not cmake_found:
        try:
            subprocess.check_call(['cmake', '--version'])
            cmake_found = True
        except Exception:
            raise Exception("'cmake' not found. cmake must be installed to build from source.")


class AwsLib(object):
    def __init__(self, name, extra_cmake_args=[]):
        self.name = name
        self.extra_cmake_args = extra_cmake_args


# The extension depends on these libs.
# They're built along with the extension, in the order listed.
AWS_LIBS = []
if sys.platform != 'darwin' and sys.platform != 'win32':
    AWS_LIBS.append(AwsLib('s2n'))
AWS_LIBS.append(AwsLib('aws-c-common'))
AWS_LIBS.append(AwsLib('aws-c-io'))
AWS_LIBS.append(AwsLib('aws-c-cal'))
AWS_LIBS.append(AwsLib('aws-c-compression'))
AWS_LIBS.append(AwsLib('aws-c-http'))
AWS_LIBS.append(AwsLib('aws-c-auth'))
AWS_LIBS.append(AwsLib('aws-c-mqtt'))


PROJECT_DIR = os.path.dirname(os.path.realpath(__file__))
DEP_BUILD_DIR = os.path.join(PROJECT_DIR, 'build', 'deps')
DEP_INSTALL_PATH = os.environ.get('AWS_C_INSTALL', os.path.join(DEP_BUILD_DIR, 'install'))


class awscrt_build_ext(setuptools.command.build_ext.build_ext):
    def _build_dependency(self, aws_lib):
        check_cmake_installed()

        prev_cwd = os.getcwd()  # restore cwd at end of function
        lib_source_dir = os.path.join(PROJECT_DIR, 'aws-common-runtime', aws_lib.name)

        build_type = 'Debug' if self.debug else 'RelWithDebInfo'

        # Skip library if it wasn't pulled
        if not os.path.exists(os.path.join(lib_source_dir, 'CMakeLists.txt')):
            print("--- Skipping dependency: '{}' source not found ---".format(aws_lib.name))
            return

        print("--- Building dependency: {} ({}) ---".format(aws_lib.name, build_type))
        lib_build_dir = os.path.join(DEP_BUILD_DIR, aws_lib.name)
        if not os.path.exists(lib_build_dir):
            os.makedirs(lib_build_dir)

        os.chdir(lib_build_dir)

        # cmake configure
        cmake_args = ['cmake']
        cmake_args.extend(determine_generator_args())
        cmake_args.extend(determine_cross_compile_args())
        cmake_args.extend([
            '-DCMAKE_PREFIX_PATH={}'.format(DEP_INSTALL_PATH),
            '-DCMAKE_INSTALL_PREFIX={}'.format(DEP_INSTALL_PATH),
            '-DBUILD_SHARED_LIBS=OFF',
            '-DCMAKE_BUILD_TYPE={}'.format(build_type),
            '-DBUILD_TESTING=OFF',
            '-DS2N_NO_PQ_ASM=ON',
        ])
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
        for lib in AWS_LIBS:
            self._build_dependency(lib)

        # update paths so awscrt_ext can access dependencies
        self.include_dirs.append(os.path.join(DEP_INSTALL_PATH, 'include'))

        # some platforms (ex: fedora) use /lib64 instead of just /lib
        lib_dir = 'lib'
        if is_64bit() and os.path.exists(os.path.join(DEP_INSTALL_PATH, 'lib64')):
            lib_dir = 'lib64'
        if is_32bit() and os.path.exists(os.path.join(DEP_INSTALL_PATH, 'lib32')):
            lib_dir = 'lib32'

        self.library_dirs.append(os.path.join(DEP_INSTALL_PATH, lib_dir))

        # continue with normal build_ext.run()
        setuptools.command.build_ext.build_ext.run(self)  # python2 breaks if we use super().run()


def awscrt_ext():
    # fetch the CFLAGS/LDFLAGS from env
    extra_compile_args = os.environ.get('CFLAGS', '').split()
    extra_link_args = os.environ.get('LDFLAGS', '').split()
    extra_objects = []

    libraries = [x.name for x in AWS_LIBS]

    # libraries must be passed to the linker with upstream dependencies listed last.
    libraries.reverse()

    if sys.platform == 'win32':
        # the windows apis being used under the hood. Since we're static linking we have to follow the entire chain down
        libraries += ['Secur32', 'Crypt32', 'Advapi32', 'BCrypt', 'Kernel32', 'Ws2_32', 'Shlwapi']
        # Ensure that debug info is in the obj files, and that it is linked into the .pyd so that
        # stack traces and dumps are useful
        extra_compile_args += ['/Z7']
        extra_link_args += ['/DEBUG']

    elif sys.platform == 'darwin':
        extra_link_args += ['-framework', 'Security']

        # HACK: Don't understand why, but if AWS_LIBS are linked normally on macos, we get this error:
        # ImportError: dlopen(_awscrt.cpython-37m-darwin.so, 2): Symbol not found: _aws_byte_cursor_eq_ignore_case
        # Workaround is to pass them as 'extra_objects' instead of 'libraries'.
        extra_objects = [os.path.join(DEP_INSTALL_PATH, 'lib', 'lib{}.a'.format(x.name)) for x in AWS_LIBS]
        libraries = []

    else:  # unix
        # linker will prefer shared libraries over static if it can find both.
        # force linker to choose static one by using using "-l:libcrypto.a" syntax instead of just "-lcrypto".
        libraries += [':libcrypto.a', 'rt']

    if distutils.ccompiler.get_default_compiler() != 'msvc':
        extra_compile_args += ['-Wextra', '-Werror', '-Wno-strict-aliasing', '-std=gnu99']

    return setuptools.Extension(
        '_awscrt',
        language='c',
        libraries=libraries,
        sources=glob.glob('source/*.c'),
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
        extra_objects=extra_objects
    )


setuptools.setup(
    name="awscrt",
    version="0.5.11",
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
    tests_require=[
        'boto3'
    ],
)
