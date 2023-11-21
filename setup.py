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
from wheel.bdist_wheel import bdist_wheel


def is_64bit():
    return sys.maxsize > 2 ** 32


def is_32bit():
    return is_64bit() == False


def is_development_mode():
    """Return whether we're building in development mode.
    https://setuptools.pypa.io/en/latest/userguide/development_mode.html
    These builds can take shortcuts to encourage faster iteration,
    and turn on more warnings as errors to encourage correct code."""
    return 'develop' in sys.argv


def run_cmd(args):
    print('>', subprocess.list2cmdline(args))
    subprocess.check_call(args)


def copy_tree(src, dst):
    if sys.version_info >= (3, 8):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)


def is_macos_universal2():
    """Return whether extension should build as an Apple universal binary (works on both x86_64 and arm64)"""
    if not sys.platform == 'darwin':
        return False

    cflags = sysconfig.get_config_var('CFLAGS')
    return '-arch x86_64' in cflags and '-arch x86_64' in cflags


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
            assert (vs_version and vs_year)
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


def using_system_libcrypto():
    return os.getenv('AWS_CRT_BUILD_USE_SYSTEM_LIBCRYPTO') == '1'


class AwsLib:
    def __init__(self, name, extra_cmake_args=[], libname=None):
        self.name = name
        self.extra_cmake_args = extra_cmake_args
        self.libname = libname if libname else name


# The extension depends on these libs.
# They're built along with the extension.
AWS_LIBS = []
if sys.platform != 'darwin' and sys.platform != 'win32':
    if not using_system_libcrypto():
        # aws-lc produces libcrypto.a
        AWS_LIBS.append(AwsLib('aws-lc', libname='crypto'))
    AWS_LIBS.append(AwsLib('s2n'))
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
    def _build_dependencies_impl(self, build_dir, install_path, osx_arch=None):
        cmake = get_cmake_path()

        # enable parallel builds for cmake 3.12+
        # setting environ because "--parallel" arg doesn't exist in older cmake versions.
        # setting a number because if it's blank then "make" will go absolutely
        # bananas and run out of memory on low-end machines.
        if 'CMAKE_BUILD_PARALLEL_LEVEL' not in os.environ:
            os.environ['CMAKE_BUILD_PARALLEL_LEVEL'] = f'{os.cpu_count()}'

        source_dir = os.path.join(PROJECT_DIR, 'crt')

        build_type = 'Debug' if self.debug else 'RelWithDebInfo'

        if osx_arch:
            print(f"--- Building arch: {osx_arch} ---")

        # cmake configure
        cmake_args = [cmake]
        cmake_args.append(f'-H{source_dir}')
        cmake_args.append(f'-B{build_dir}')
        cmake_args.extend(determine_generator_args())
        cmake_args.extend(determine_cross_compile_args())
        cmake_args.extend([
            f'-DCMAKE_INSTALL_PREFIX={install_path}',
            f'-DCMAKE_BUILD_TYPE={build_type}',
        ])

        if using_system_libcrypto():
            cmake_args.append('-DUSE_OPENSSL=ON')

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
            '--build', build_dir,
            '--config', build_type,
            '--target', 'install',
        ]
        run_cmd(build_cmd)

    def _build_dependencies(self, build_dir, install_path):
        if is_macos_universal2() and not is_development_mode():
            # create macOS universal binary by compiling for x86_64 and arm64,
            # each in its own subfolder, and then creating a universal binary
            # by gluing the two together using `lipo`.
            #
            # The AWS C libs don't support building for multiple architectures
            # simultaneously (too much confusion at cmake configure time).
            # So we build each architecture one at a time.
            #
            # BUT skip this in development mode. Building everything twice takes
            # too long and development builds only ever run on the host machine.

            # x86_64
            self._build_dependencies_impl(
                build_dir=os.path.join(build_dir, 'x86_64'),
                install_path=os.path.join(build_dir, 'x86_64', 'install'),
                osx_arch='x86_64')

            # arm64
            self._build_dependencies_impl(
                build_dir=os.path.join(build_dir, 'arm64'),
                install_path=os.path.join(build_dir, 'arm64', 'install'),
                osx_arch='arm64')

            # Create a universal binary for each lib at expected install_path
            lib_dir = os.path.join(install_path, 'lib')
            os.makedirs(lib_dir, exist_ok=True)
            for aws_lib in AWS_LIBS:
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
            self._build_dependencies_impl(build_dir, install_path)

    def run(self):
        # build dependencies
        dep_build_dir = os.path.join(self.build_temp, 'deps')
        dep_install_path = os.path.join(self.build_temp, 'deps', 'install')

        if os.path.exists(os.path.join(PROJECT_DIR, 'crt', 'aws-c-common', 'CMakeLists.txt')):
            self._build_dependencies(dep_build_dir, dep_install_path)
        else:
            print("Skip building dependencies, source not found.")

        # update paths so awscrt_ext can access dependencies.
        # add to the front of any list so that our dependencies are preferred
        # over anything that might already be on the system (i.e. libcrypto.a)

        self.include_dirs.insert(0, os.path.join(dep_install_path, 'include'))

        # some platforms (ex: fedora) use /lib64 instead of just /lib
        lib_dir = 'lib'
        if is_64bit() and os.path.exists(os.path.join(dep_install_path, 'lib64')):
            lib_dir = 'lib64'
        if is_32bit() and os.path.exists(os.path.join(dep_install_path, 'lib32')):
            lib_dir = 'lib32'

        self.library_dirs.insert(0, os.path.join(dep_install_path, lib_dir))

        # continue with normal build_ext.run()
        super().run()


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()
        if python.startswith("cp") and sys.version_info >= (3, 11):
            # on CPython, our wheels are abi3 and compatible back to 3.11
            return "cp311", "abi3", plat

        return python, abi, plat


def awscrt_ext():
    # fetch the CFLAGS/LDFLAGS from env
    extra_compile_args = os.environ.get('CFLAGS', '').split()
    extra_link_args = os.environ.get('LDFLAGS', '').split()
    extra_objects = []
    define_macros = []
    py_limited_api = False

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
        # force linker to choose static variant by using using
        # "-l:libaws-c-common.a" syntax instead of just "-laws-c-common".
        #
        # This helps AWS developers creating Lambda applications from Brazil.
        # In Brazil, both shared and static libs are available.
        # But Lambda requires all shared libs to be explicitly packaged up.
        # So it's simpler to link them in statically and have less runtime dependencies.
        libraries = [':lib{}.a'.format(x) for x in libraries]

        # OpenBSD doesn't have librt; functions are found in libc instead.
        if not sys.platform.startswith('openbsd'):
            libraries += ['rt']

        if using_system_libcrypto():
            libraries += ['crypto']

        # FreeBSD doesn't have execinfo as a part of libc like other Unix variant.
        # Passing linker flag to link execinfo properly
        if sys.platform.startswith('freebsd'):
            extra_link_args += ['-lexecinfo']

        # hide the symbols from libcrypto.a
        # this prevents weird crashes if an application also ends up using
        # libcrypto.so from the system's OpenSSL installation.
        extra_link_args += ['-Wl,--exclude-libs,libcrypto.a']

        # python usually adds -pthread automatically, but we've observed
        # rare cases where that didn't happen, so let's be explicit.
        extra_link_args += ['-pthread']

    if distutils.ccompiler.get_default_compiler() != 'msvc':
        extra_compile_args += ['-Wno-strict-aliasing', '-std=gnu99']

        # treat warnings as errors in development mode
        if is_development_mode() or os.getenv('AWS_CRT_BUILD_WARNINGS_ARE_ERRORS') == '1':
            extra_compile_args += ['-Wextra', '-Werror']

            # ...except when we take shortcuts in development mode and don't make
            # a proper MacOS Universal2 binary. The linker warns us about this,
            # but WHATEVER. Building everything twice (x86_64 and arm64) takes too long.
            if not is_macos_universal2():
                if sys.platform == 'darwin':
                    extra_link_args += ['-Wl,-fatal_warnings']
                elif 'bsd' in sys.platform:
                    extra_link_args += ['-Wl,-fatal-warnings']
                else:
                    extra_link_args += ['-Wl,--fatal-warnings']

    if sys.version_info >= (3, 11):
        define_macros.append(('Py_LIMITED_API', '0x030B0000'))
        py_limited_api = True

    return setuptools.Extension(
        '_awscrt',
        language='c',
        libraries=libraries,
        sources=glob.glob('source/*.c'),
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
        extra_objects=extra_objects,
        define_macros=define_macros,
        py_limited_api=py_limited_api,
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
    python_requires='>=3.7',
    ext_modules=[awscrt_ext()],
    cmdclass={'build_ext': awscrt_build_ext, "bdist_wheel": bdist_wheel_abi3},
    test_suite='test',
)
