# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
cmake_minimum_required(VERSION 3.1)

# This CMakeLists.txt exists so we can build all the C libraries we depend on
# simultaneously. This is much faster than building dependencies one at a time.
#
# This CMakeLists.txt does NOT build the Python extension itself.
# We let setuptools handle that.
project(aws-crt-dependencies)

# Note: set() calls must use CACHE, and must be called before the option() they're overriding,
# or they won't work right on CMake 3.12 and below.
# see: https://cmake.org/cmake/help/v3.13/policy/CMP0077.html

# This magic lets us build everything all at once
set(IN_SOURCE_BUILD ON CACHE BOOL "")
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/aws-c-common/cmake)
include(AwsFindPackage)

# Build dependencies as static libs
set(BUILD_SHARED_LIBS OFF CACHE BOOL "")
set(CMAKE_POSITION_INDEPENDENT_CODE ON CACHE BOOL "")

# Don't build the dependencies' tests
set(BUILD_TESTING OFF CACHE BOOL "")
include(CTest)

# On Unix we use S2N for TLS and AWS-LC crypto.
# (On Windows and Apple we use the default OS libraries)
if(UNIX AND NOT APPLE)
    option(USE_OPENSSL "Set this if you want to use your system's OpenSSL compatible libcrypto" OFF)

    if(NOT USE_OPENSSL)
        set(DISABLE_GO ON CACHE BOOL "Build without using Go, we don't want the extra dependency")
        set(BUILD_LIBSSL OFF CACHE BOOL "Don't need libssl, only need libcrypto")

        if(CMAKE_C_COMPILER_ID MATCHES "GNU" AND CMAKE_C_COMPILER_VERSION VERSION_LESS "5.0")
            set(DISABLE_PERL OFF CACHE BOOL "Build with Perl to avoid using pre-compiled binary with AVX512")
            set(MY_ASSEMBLER_IS_TOO_OLD_FOR_512AVX ON CACHE BOOL "Disable AVX512 on old GCC that not supports it")
        else()
            set(DISABLE_PERL ON CACHE BOOL "Build without using Perl, we don't want the extra dependency")
        endif()

        add_subdirectory(aws-lc)
    endif()

    set(UNSAFE_TREAT_WARNINGS_AS_ERRORS OFF CACHE BOOL "")
    add_subdirectory(s2n)
endif()

add_subdirectory(aws-c-common)
add_subdirectory(aws-c-sdkutils)
add_subdirectory(aws-c-cal)
add_subdirectory(aws-c-io)
add_subdirectory(aws-checksums)
add_subdirectory(aws-c-compression)
add_subdirectory(aws-c-event-stream)
add_subdirectory(aws-c-http)
add_subdirectory(aws-c-auth)
add_subdirectory(aws-c-mqtt)
add_subdirectory(aws-c-s3)
