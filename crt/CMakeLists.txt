# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.
cmake_minimum_required(VERSION 3.1)
project(aws-crt-dependencies)

# This magic lets us build everything all at once
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/aws-c-common/cmake)
include(AwsFindPackage)
set(IN_SOURCE_BUILD ON)

# Always build static libs
set(BUILD_SHARED_LIBS=OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE=ON)

# Don't build the dependencies' tests
include(CTest)
set(BUILD_TESTING OFF)

if(UNIX AND NOT APPLE)
    set(DISABLE_GO ON) # Build without using go, we don't want the extra dependency
    set(DISABLE_PERL ON) # Build without using perl, we don't want the extra dependency
    set(BUILD_LIBSSL OFF) # Don't need libssl, only need libcrypto
    add_subdirectory(aws-lc)

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
