# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
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

if sys.platform == 'win32':
    # distutils is deprecated in Python 3.10 and removed in 3.12. However, it still works because Python defines a compatibility interface as long as setuptools is installed.
    # We don't have an official alternative for distutils.ccompiler as of September 2024. See: https://github.com/pypa/setuptools/issues/2806
    # Once that issue is resolved, we can migrate to the official solution.
    # For now, restrict distutils to Windows only, where it's needed.
    import distutils.ccompiler

# The minimum MACOSX_DEPLOYMENT_TARGET required for the library. If not
# set, the library will use the default value from python
# sysconfig.get_config_var('MACOSX_DEPLOYMENT_TARGET').
MACOS_DEPLOYMENT_TARGET_MIN = "10.15"

# This is the minimum version of the Windows SDK needed for schannel.h with SCH_CREDENTIALS and
# TLS_PARAMETERS. These are required to build Windows Binaries with TLS 1.3 support.
WINDOWS_SDK_VERSION_TLS1_3_SUPPORT = "10.0.17763.0"


def parse_version(version_string):
    return tuple(int(x) for x in version_string.split("."))


def is_64bit():
    return sys.maxsize > 2 ** 32


def is_32bit():
    return is_64bit() == False


# TODO: Fix this. Since adding pyproject.toml, it always returns False
def is_development_mode():
    """Return whether we're building in Development Mode (a.k.a. “Editable Installs”).
    https://setuptools.pypa.io/en/latest/userguide/development_mode.html
    These builds can take shortcuts to encourage faster iteration,
    and turn on more warnings as errors to encourage correct code."""
    return 'develop' in sys.argv


def get_xcode_major_version():
    """Return major version of xcode present on the system"""
    try:
        output = subprocess.check_output(
            ['xcodebuild', '-version'], text=True)
        version_line = output.split('\n')[0]
        version = version_line.split(' ')[-1]
        return int(version.split('.')[0])
    except BaseException:
        return 0


def run_cmd(args):
    print('>', subprocess.list2cmdline(args))
    subprocess.check_call(args)


def copy_tree(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def is_macos_universal2():
    """Return whether extension should build as an Apple universal binary (works on both x86_64 and arm64)"""
    if not sys.platform == 'darwin':
        return False

    cflags = sysconfig.get_config_var('CFLAGS')
    return '-arch x86_64' in cflags and '-arch arm64' in cflags


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
        vs_version_gen_str = "Visual Studio {} {}".format(vs_version, vs_year)

        if vs_year <= 2017:
            # For VS2017 and earlier, architecture goes at end of generator string
            if is_64bit():
                vs_version_gen_str += " Win64"
            return ['-G', vs_version_gen_str]

        # For VS2019 (and presumably later), architecture is passed via -A flag
        arch_str = "x64" if is_64bit() else "Win32"

        windows_sdk_version = os.getenv('AWS_CRT_WINDOWS_SDK_VERSION')
        if windows_sdk_version is None:
            windows_sdk_version = WINDOWS_SDK_VERSION_TLS1_3_SUPPORT

        # Set the target windows SDK version. We have a minimum required version of the Windows SDK needed for schannel.h with SCH_CREDENTIALS and
        # TLS_PARAMETERS. These are required to build Windows Binaries with TLS 1.3 support.
        # Introduced in cmake 3.27+, the generator string supports a version field to specify the windows sdk version in use
        # https://cmake.org/cmake/help/latest/variable/CMAKE_GENERATOR_PLATFORM.html#variable:CMAKE_GENERATOR_PLATFORM
        if get_cmake_version() >= (3, 27):
            # Set windows sdk version to the one that supports TLS 1.3
            arch_str += f",version={AWS_CRT_WINDOWS_SDK_VERSION}"
        else:
            # for cmake < 3.27, we have to specify the version with CMAKE_SYSTEM_VERSION. Please note this flag will be
            # ignored by cmake versions >= 3.27.
            arch_str += f" -DCMAKE_SYSTEM_VERSION={AWS_CRT_WINDOWS_SDK_VERSION}"

        print('Using Visual Studio', vs_version, vs_year, 'with architecture', arch_str)

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


def get_cmake_version():
    """Return the version of CMake installed on the system."""
    cmake_path = get_cmake_path()
    if not cmake_path:
        return (0, 0, 0)
    try:
        output = subprocess.check_output([cmake_path, '--version'], text=True)
        version_line = output.split('\n')[0]
        version = version_line.split(' ')[-1]
        print(f"Found CMake version: {version}")
        return parse_version(version)
    except BaseException:
        return (0, 0, 0)  # Return a default version if cmake is not found or fails


def using_system_libs():
    """If true, don't build any dependencies. Use the libs that are already on the system."""
    return (os.getenv('AWS_CRT_BUILD_USE_SYSTEM_LIBS') == '1'
            or not os.path.exists(os.path.join(PROJECT_DIR, 'crt', 'aws-c-common', 'CMakeLists.txt')))


def using_libcrypto():
    """If true, libcrypto is used, even on win/mac."""
    if sys.platform == 'darwin' or sys.platform == 'win32':
        # use libcrypto on mac/win to support ed25519, unless its disabled via env-var
        return not os.getenv('AWS_CRT_BUILD_DISABLE_LIBCRYPTO_USE_FOR_ED25519_EVERYWHERE') == '1'
    else:
        # on Unix we always use libcrypto
        return True


def using_system_libcrypto():
    """If true, don't build AWS-LC. Use the libcrypto that's already on the system."""
    return using_system_libs() or os.getenv('AWS_CRT_BUILD_USE_SYSTEM_LIBCRYPTO') == '1'


def forcing_static_libs():
    """If true, force libs to be linked statically."""
    return os.getenv('AWS_CRT_BUILD_FORCE_STATIC_LIBS') == '1'


class AwsLib:
    def __init__(self, name, extra_cmake_args=[], libname=None):
        self.name = name
        self.extra_cmake_args = extra_cmake_args
        self.libname = libname if libname else name


# The extension depends on these libs.
# They're built along with the extension (unless using_system_libs() is True)
AWS_LIBS = []

if using_libcrypto():
    # aws-lc produces libcrypto.a
    AWS_LIBS.append(AwsLib('aws-lc', libname='crypto'))

if sys.platform != 'darwin' and sys.platform != 'win32':
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

        if using_libcrypto():
            if using_system_libcrypto():
                cmake_args.append('-DUSE_OPENSSL=ON')

            cmake_args.append('-DAWS_USE_LIBCRYPTO_TO_SUPPORT_ED25519_EVERYWHERE=ON')

        if sys.platform == 'darwin':
            # get Python's MACOSX_DEPLOYMENT_TARGET version
            macosx_target_ver = sysconfig.get_config_var('MACOSX_DEPLOYMENT_TARGET')
            # If MACOS_DEPLOYMENT_TARGET_MIN is set to a later version than python distribution,
            # override MACOSX_DEPLOYMENT_TARGET.
            if macosx_target_ver is None or parse_version(
                    MACOS_DEPLOYMENT_TARGET_MIN) > parse_version(macosx_target_ver):
                macosx_target_ver = MACOS_DEPLOYMENT_TARGET_MIN
                os.environ['MACOSX_DEPLOYMENT_TARGET'] = macosx_target_ver
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

    def _build_dependencies(self):
        build_dir = os.path.join(self.build_temp, 'deps')
        install_path = os.path.join(self.build_temp, 'deps', 'install')

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

        # update paths so awscrt_ext can access dependencies.
        # add to the front of any list so that our dependencies are preferred
        # over anything that might already be on the system (i.e. libcrypto.a)

        self.include_dirs.insert(0, os.path.join(install_path, 'include'))

        # some platforms (ex: fedora) use /lib64 instead of just /lib
        lib_dir = 'lib'
        if is_64bit() and os.path.exists(os.path.join(install_path, 'lib64')):
            lib_dir = 'lib64'
        if is_32bit() and os.path.exists(os.path.join(install_path, 'lib32')):
            lib_dir = 'lib32'

        self.library_dirs.insert(0, os.path.join(install_path, lib_dir))

    def run(self):
        if using_system_libs():
            print("Skip building dependencies")
        else:
            self._build_dependencies()

        # continue with normal build_ext.run()
        super().run()


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()
        # on CPython, our wheels are abi3 and compatible back to 3.11
        if python.startswith("cp") and sys.version_info >= (3, 13):
            # 3.13 deprecates PyWeakref_GetObject(), adds alternative
            return "cp313", "abi3", plat
        elif python.startswith("cp") and sys.version_info >= (3, 11):
            # 3.11 is the first stable ABI that has everything we need
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
        if forcing_static_libs():
            # linker will prefer shared libraries over static if it can find both.
            # force linker to choose static variant by using
            # "-l:libaws-c-common.a" syntax instead of just "-laws-c-common".
            #
            # This helps AWS developers creating Lambda applications from Brazil.
            # In Brazil, both shared and static libs are available.
            # But Lambda requires all shared libs to be explicitly packaged up.
            # So it's simpler to link them in statically and have less runtime dependencies.
            #
            # Don't apply this trick to dependencies that are always on the OS (e.g. librt)
            libraries = [':lib{}.a'.format(x) for x in libraries]

        # OpenBSD doesn't have librt; functions are found in libc instead.
        if not sys.platform.startswith('openbsd'):
            libraries += ['rt']

        # OpenBSD 7.4+ defaults to linking with --execute-only, which is bad for AWS-LC.
        # See: https://github.com/aws/aws-lc/blob/4b07805bddc55f68e5ce8c42f215da51c7a4e099/CMakeLists.txt#L44-L53
        # (If AWS-LC's CMakeLists.txt removes these lines in the future, we can remove this hack here as well)
        if sys.platform.startswith('openbsd'):
            if not using_system_libcrypto():
                extra_link_args += ['-Wl,--no-execute-only']

        # FreeBSD doesn't have execinfo as a part of libc like other Unix variant.
        # Passing linker flag to link execinfo properly
        if sys.platform.startswith('freebsd'):
            libraries += ['execinfo']

        # python usually adds -pthread automatically, but we've observed
        # rare cases where that didn't happen, so let's be explicit.
        extra_link_args += ['-pthread']

        # hide the symbols from libcrypto.a
        # this prevents weird crashes if an application also ends up using
        # libcrypto.so from the system's OpenSSL installation.
        # Do this even if using system libcrypto, since it could still be a static lib.
        extra_link_args += ['-Wl,--exclude-libs,libcrypto.a']

    if sys.platform != 'win32' or distutils.ccompiler.get_default_compiler() != 'msvc':
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
                    # xcode 15 introduced a new linker that generates a warning
                    # when it sees duplicate libs or rpath during bundling.
                    # pyenv installed from homebrew put duplicate rpath entries
                    # into sysconfig, and setuptools happily passes them along
                    # to xcode, resulting in a warning
                    # (which is fatal in this branch).
                    # ex. https://github.com/pyenv/pyenv/issues/2890
                    # lets revert back to old linker on xcode >= 15 until one of
                    # the involved parties fixes the issue.
                    if get_xcode_major_version() >= 15:
                        extra_link_args += ['-Wl,-ld_classic']
                elif 'bsd' in sys.platform:
                    extra_link_args += ['-Wl,-fatal-warnings']
                else:
                    extra_link_args += ['-Wl,--fatal-warnings']

    # prefer building with stable ABI, so a wheel can work with multiple major versions
    if sys.version_info >= (3, 13):
        # 3.13 deprecates PyWeakref_GetObject(), adds alternative
        define_macros.append(('Py_LIMITED_API', '0x030D0000'))
        py_limited_api = True
    elif sys.version_info >= (3, 11):
        # 3.11 is the first stable ABI that has everything we need
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


def _load_version():
    init_path = os.path.join(PROJECT_DIR, 'awscrt', '__init__.py')
    with open(init_path) as fp:
        return VERSION_RE.match(fp.read()).group(1)


setuptools.setup(
    version=_load_version(),
    # Note: find_packages() without extra args will end up installing test/
    packages=setuptools.find_packages(include=['awscrt*']),
    ext_modules=[awscrt_ext()],
    cmdclass={'build_ext': awscrt_build_ext, "bdist_wheel": bdist_wheel_abi3},
)
