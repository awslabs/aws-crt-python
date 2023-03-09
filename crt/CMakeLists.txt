# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
cmake_minimum_required(VERSION 3.1)

# This CMakeLists.txt exists so we can build all the C libraries we depend on
# simultaneously. This is much faster than building dependencies one at a time.
#
# This CMakeLists.txt does NOT build the Python extension itself.
# We let setuptools handle that.
project(aws-crt-dependencies)

# This magic lets us build everything all at once
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/aws-c-common/cmake)
include(AwsFindPackage)
set(IN_SOURCE_BUILD ON)

# Build dependencies as static libs
set(BUILD_SHARED_LIBS=OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE=ON)

# Don't build the dependencies' tests
include(CTest)
set(BUILD_TESTING OFF)

# On Unix we use S2N for TLS and AWS-LC crypto.
# (On Windows and Apple we use the default OS libraries)
if(UNIX AND NOT APPLE)
    set(DISABLE_GO ON) # Build without using Go, we don't want the extra dependency
    set(DISABLE_PERL ON) # Build without using Perl, we don't want the extra dependency
    set(BUILD_LIBSSL OFF) # Don't need libssl, only need libcrypto

    option(USE_OPENSSL "Set this if you want to use your system's OpenSSL compatible libcrypto" OFF)
    if (NOT USE_OPENSSL)
        add_subdirectory(aws-lc)
    endif()

    set(UNSAFE_TREAT_WARNINGS_AS_ERRORS OFF)
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
