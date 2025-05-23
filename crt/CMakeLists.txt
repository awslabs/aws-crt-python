# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
cmake_minimum_required(VERSION 3.9...3.31)

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

option(AWS_USE_LIBCRYPTO_TO_SUPPORT_ED25519_EVERYWHERE "Set this if you want to use libcrypto to support ed25519 on Window/Apple" ON)

# Use minimal debug info to reduce binary size.
string(REPLACE "-g" "-g1" CMAKE_CXX_FLAGS_RELWITHDEBINFO "${CMAKE_CXX_FLAGS_RELWITHDEBINFO}")
string(REPLACE "-g" "-g1" CMAKE_C_FLAGS_RELWITHDEBINFO "${CMAKE_C_FLAGS_RELWITHDEBINFO}")

# On Unix we use S2N for TLS and AWS-LC crypto.
# (On Windows and Apple we use the default OS libraries)
if ((UNIX AND NOT APPLE) OR AWS_USE_LIBCRYPTO_TO_SUPPORT_ED25519_EVERYWHERE)
    option(USE_OPENSSL "Set this if you want to use your system's OpenSSL compatible libcrypto" OFF)
    include(AwsPrebuildDependency)

    if(NOT USE_OPENSSL)

        set(AWSLC_CMAKE_ARGUMENTS
            -DDISABLE_GO=ON  # Build without using Go, we don't want the extra dependency
            -DDISABLE_PERL=ON  # Build without using Perl, we don't want the extra dependency
            -DBUILD_LIBSSL=OFF  # Don't need libssl, only need libcrypto
            -DBUILD_TESTING=OFF
            -DCMAKE_BUILD_TYPE=RelWithDebInfo  # Use the same build type as the rest of the project
        )

        if (APPLE OR WIN32)
            # Libcrypto implementations typically have several chunky pregenerated tables that add a lot
            # to artifact size. We dont really need them for ed25519 case on win/mac, so favor
            # smaller binary over perf here.
            # In future if there is more usage of lc on win/mac consider removing this
            list(APPEND AWSLC_CMAKE_ARGUMENTS -DOPENSSL_SMALL=1)
        endif()

        if(CMAKE_C_COMPILER_ID MATCHES "GNU" AND CMAKE_C_COMPILER_VERSION VERSION_LESS "5.0")
            # Disable AVX512 on old GCC that not supports it.
            list(APPEND AWSLC_CMAKE_ARGUMENTS -DMY_ASSEMBLER_IS_TOO_OLD_FOR_512AVX=ON)
        endif()

        # s2n-tls uses libcrypto during its configuration, so we need to prebuild aws-lc.
        aws_prebuild_dependency(
            DEPENDENCY_NAME AWSLC
            SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/aws-lc
            CMAKE_ARGUMENTS ${AWSLC_CMAKE_ARGUMENTS}
        )
    endif()


endif()

if(UNIX AND NOT APPLE)
    # prebuild s2n-tls.
    aws_prebuild_dependency(
        DEPENDENCY_NAME S2N
        SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/s2n
        CMAKE_ARGUMENTS
            -DUNSAFE_TREAT_WARNINGS_AS_ERRORS=OFF
            -DBUILD_TESTING=OFF
    )
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
