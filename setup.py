# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import codecs
import distutils.ccompiler
import glob
import os
import os.path
import platform
import re
import setuptools
import setuptools.command.build_ext
import shutil
import subprocess
import sys
import sysconfig


def is_64bit():
    return sys.maxsize > 2**32


def is_32bit():
    return is_64bit() == False


def run_cmd(args):
    print('>', subprocess.list2cmdline(args))
    subprocess.check_call(args)


def copy_tree(src, dst):
    if sys.version_info >= (3, 8):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)


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
            if '\\Microsoft Visual Studio\\2022' in compiler.cc:
                vs_version = 17
                vs_year = 2022
            elif '\\Microsoft Visual Studio\\2019' in compiler.cc:
                vs_version = 16
                vs_year = 2019
            elif '\\Microsoft Visual Studio\\2017' in compiler.cc:
                vs_version = 15
                vs_year = 2017
            elif '\\Microsoft Visual Studio 14.0' in compiler.cc:
                vs_version = 14
                vs_year = 2015
            assert(vs_version and vs_year)
        except Exception:
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


cmake_found = None


def get_cmake_path():
    global cmake_found
    if cmake_found:
        return cmake_found

    for cmake_alias in ['cmake3', 'cmake']:
        cmake_found = shutil.which(cmake_alias)
        if cmake_found:
            return cmake_found

    raise Exception("CMake must be installed to build from source.")


class AwsLib:
    def __init__(self, name, extra_cmake_args=[], libname=None):
        self.name = name
        self.extra_cmake_args = extra_cmake_args
        self.libname = libname if libname else name


# The extension depends on these libs.
# They're built along with the extension, in the order listed.
AWS_LIBS = []
if sys.platform != 'darwin' and sys.platform != 'win32':
    AWS_LIBS.append(AwsLib(name='aws-lc',
                           libname='crypto',  # We link against libcrypto.a
                           extra_cmake_args=[
                               # We don't need libssl.a
                               '-DBUILD_LIBSSL=OFF',
                               # Disable running codegen on user's machine.
                               # Up-to-date generated code is already in repo.
                               '-DDISABLE_PERL=ON', '-DDISABLE_GO=ON',
                           ]))
    AWS_LIBS.append(AwsLib(name='s2n', extra_cmake_args=['-DUNSAFE_TREAT_WARNINGS_AS_ERRORS=OFF']))
AWS_LIBS.append(AwsLib('aws-c-common'))
AWS_LIBS.append(AwsLib('aws-c-sdkutils'))
AWS_LIBS.append(AwsLib('aws-c-cal'))
AWS_LIBS.append(AwsLib('aws-c-io'))
AWS_LIBS.append(AwsLib('aws-checksums'))
AWS_LIBS.append(AwsLib('aws-c-compression'))
AWS_LIBS.append(AwsLib('aws-c-event-stream'))
AWS_LIBS.append(AwsLib('aws-c-http'))
AWS_LIBS.append(AwsLib('aws-c-auth'))
AWS_LIBS.append(AwsLib('aws-c-mqtt'))
AWS_LIBS.append(AwsLib('aws-c-s3'))


PROJECT_DIR = os.path.dirname(os.path.realpath(__file__))

VERSION_RE = re.compile(r""".*__version__ = ["'](.*?)['"]""", re.S)


class awscrt_build_ext(setuptools.command.build_ext.build_ext):
    def _build_dependency_impl(self, aws_lib, build_dir, install_path, osx_arch=None):
        cmake = get_cmake_path()

        # enable parallel builds for cmake 3.12+
        # setting environ because "--parallel" arg doesn't exist in older cmake versions.
        # setting a number because if it's blank then "make" will go absolutely
        # bananas and run out of memory on low-end machines.
        if 'CMAKE_BUILD_PARALLEL_LEVEL' not in os.environ:
            os.environ['CMAKE_BUILD_PARALLEL_LEVEL'] = f'{os.cpu_count()}'

        lib_source_dir = os.path.join(PROJECT_DIR, 'crt', aws_lib.name)

        build_type = 'Debug' if self.debug else 'RelWithDebInfo'

        if osx_arch:
            print(f"--- Building dependency: {aws_lib.name} ({osx_arch}) ---")
        else:
            print(f"--- Building dependency: {aws_lib.name} ---")

        lib_build_dir = os.path.join(build_dir, aws_lib.name)
        os.makedirs(lib_build_dir, exist_ok=True)

        # cmake configure
        cmake_args = [cmake]
        cmake_args.append(f'-H{lib_source_dir}')
        cmake_args.append(f'-B{lib_build_dir}')
        cmake_args.extend(determine_generator_args())
        cmake_args.extend(determine_cross_compile_args())
        cmake_args.extend([
            f'-DCMAKE_PREFIX_PATH={os.path.abspath(install_path)}',
            f'-DCMAKE_INSTALL_PREFIX={install_path}',
            '-DBUILD_SHARED_LIBS=OFF',
            f'-DCMAKE_BUILD_TYPE={build_type}',
            '-DBUILD_TESTING=OFF',
            '-DCMAKE_POSITION_INDEPENDENT_CODE=ON'
        ])

        cmake_args.extend(aws_lib.extra_cmake_args)

        if sys.platform == 'darwin':
            # build lib with same MACOSX_DEPLOYMENT_TARGET that python will ultimately
            # use to link everything together, otherwise there will be linker warnings.
            macosx_target_ver = sysconfig.get_config_var('MACOSX_DEPLOYMENT_TARGET')
            if macosx_target_ver and 'MACOSX_DEPLOYMENT_TARGET' not in os.environ:
                cmake_args.append(f'-DCMAKE_OSX_DEPLOYMENT_TARGET={macosx_target_ver}')

            if osx_arch:
                cmake_args.append(f'-DCMAKE_OSX_ARCHITECTURES={osx_arch}')

        run_cmd(cmake_args)

        # cmake build/install
        build_cmd = [
            cmake,
            '--build', lib_build_dir,
            '--config', build_type,
            '--target', 'install',
        ]
        run_cmd(build_cmd)

    def _build_dependency(self, aws_lib, build_dir, install_path):
        if sys.platform == 'darwin' and self.plat_name.endswith('universal2'):
            # create macOS universal binary by compiling for x86_64 and arm64,
            # each in its own subfolder, and then creating a universal binary
            # by gluing the two together using `lipo`.

            # x86_64
            self._build_dependency_impl(
                aws_lib=aws_lib,
                build_dir=os.path.join(build_dir, 'x86_64'),
                install_path=os.path.join(build_dir, 'x86_64', 'install'),
                osx_arch='x86_64')

            # arm64
            self._build_dependency_impl(
                aws_lib=aws_lib,
                build_dir=os.path.join(build_dir, 'arm64'),
                install_path=os.path.join(build_dir, 'arm64', 'install'),
                osx_arch='arm64')

            # create universal binary at expected install_path
            lib_dir = os.path.join(install_path, 'lib')
            os.makedirs(lib_dir, exist_ok=True)
            lib_file = f'lib{aws_lib.libname}.a'
            run_cmd(['lipo', '-create',
                     '-output', os.path.join(lib_dir, lib_file),
                     os.path.join(build_dir, 'x86_64', 'install', 'lib', lib_file),
                     os.path.join(build_dir, 'arm64', 'install', 'lib', lib_file)])

            # copy headers to expected install_path
            copy_tree(os.path.join(build_dir, 'arm64', 'install', 'include'),
                      os.path.join(install_path, 'include'))

        else:
            # normal build for a single architecture
            self._build_dependency_impl(aws_lib, build_dir, install_path)

    def run(self):
        # build dependencies
        dep_build_dir = os.path.join(self.build_temp, 'deps')
        dep_install_path = os.path.join(self.build_temp, 'deps', 'install')
        for lib in AWS_LIBS:
            self._build_dependency(lib, dep_build_dir, dep_install_path)

        # update paths so awscrt_ext can access dependencies
        self.include_dirs.append(os.path.join(dep_install_path, 'include'))

        # some platforms (ex: fedora) use /lib64 instead of just /lib
        lib_dir = 'lib'
        if is_64bit() and os.path.exists(os.path.join(dep_install_path, 'lib64')):
            lib_dir = 'lib64'
        if is_32bit() and os.path.exists(os.path.join(dep_install_path, 'lib32')):
            lib_dir = 'lib32'

        self.library_dirs.append(os.path.join(dep_install_path, lib_dir))

        # continue with normal build_ext.run()
        super().run()


def awscrt_ext():
    # fetch the CFLAGS/LDFLAGS from env
    extra_compile_args = os.environ.get('CFLAGS', '').split()
    extra_link_args = os.environ.get('LDFLAGS', '').split()
    extra_objects = []

    libraries = [x.libname for x in AWS_LIBS]

    # libraries must be passed to the linker with upstream dependencies listed last.
    libraries.reverse()

    if sys.platform == 'win32':
        # the windows apis being used under the hood. Since we're static linking we have to follow the entire chain down
        libraries += ['Secur32', 'Crypt32', 'Advapi32', 'NCrypt', 'BCrypt', 'Kernel32', 'Ws2_32', 'Shlwapi']
        # Ensure that debug info is in the obj files, and that it is linked into the .pyd so that
        # stack traces and dumps are useful
        extra_compile_args += ['/Z7']
        extra_link_args += ['/DEBUG']

    elif sys.platform == 'darwin':
        extra_link_args += ['-framework', 'Security']

    else:  # unix
        # linker will prefer shared libraries over static if it can find both.
        # force linker to choose static variant by using using "-l:libcrypto.a" syntax instead of just "-lcrypto".
        libraries = [':lib{}.a'.format(x) for x in libraries]
        libraries += ['rt']

        # python usually adds -pthread automatically, but we've observed
        # rare cases where that didn't happen, so let's be explicit.
        extra_link_args += ['-pthread']

    if distutils.ccompiler.get_default_compiler() != 'msvc':
        extra_compile_args += ['-Wextra', '-Werror', '-Wno-strict-aliasing', '-std=gnu99']
        extra_link_args += ['-Wl,-fatal_warnings']

    return setuptools.Extension(
        '_awscrt',
        language='c',
        libraries=libraries,
        sources=glob.glob('source/*.c'),
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
        extra_objects=extra_objects
    )


def _load_readme():
    readme_path = os.path.join(PROJECT_DIR, 'README.md')
    with codecs.open(readme_path, 'r', 'utf-8') as f:
        return f.read()


def _load_version():
    init_path = os.path.join(PROJECT_DIR, 'awscrt', '__init__.py')
    with open(init_path) as fp:
        return VERSION_RE.match(fp.read()).group(1)


setuptools.setup(
    name="awscrt",
    version=_load_version(),
    license="Apache 2.0",
    author="Amazon Web Services, Inc",
    author_email="aws-sdk-common-runtime@amazon.com",
    description="A common runtime for AWS Python projects",
    long_description=_load_readme(),
    long_description_content_type='text/markdown',
    url="https://github.com/awslabs/aws-crt-python",
    # Note: find_packages() without extra args will end up installing test/
    packages=setuptools.find_packages(include=['awscrt*']),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    ext_modules=[awscrt_ext()],
    cmdclass={'build_ext': awscrt_build_ext},
    test_suite='test',
    tests_require=[
        'boto3'
    ]
)
