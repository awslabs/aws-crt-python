#!/usr/bin/env bash

# usage:
# ./build-deps.sh
#   -c, --clean - remove any cached CMake config before building
#   -i, --install <path> - sets the CMAKE_INSTALL_PREFIX, the root where the deps will be install
#   <all other args> - will be passed to cmake as-is

# everything is relative to the directory this script is in
home_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

# where to have cmake put its binaries
deps_dir=$home_dir/build/deps
# where deps will be installed
install_prefix=$deps_dir/install
# whether or not to look for local sources for deps, they should be in
# the same parent directory as this repo
prefer_local_deps=0

cmake_args=""

function install_dep {
    local dep=$1
    local commit_or_branch=$2

    if [ $prefer_local_deps -ne 0 ]; then
        if [ -d $home_dir/../$dep ]; then
            pushd $home_dir/../$dep
        fi
    else # git clone the repo and build it
        pushd $deps_dir
        if [ -d $dep ]; then
            cd $dep
            git pull --rebase
        else
            git clone https://github.com/awslabs/$dep.git
            cd $dep
        fi

        if [ -n "$commit_or_branch" ]; then
            git checkout $commit_or_branch
        fi
    fi

    mkdir -p dep-build
    cd dep-build

    cmake -GNinja $cmake_args -DCMAKE_INSTALL_PREFIX=$install_prefix ..
    cmake --build . --target all
    cmake --build . --target install

    popd
}

cmake_args=()
while [[ $# -gt 0 ]]
do
    arg="$1"

    case $arg in
        -c|--clean)
        clean=1
        shift
        ;;
        -i|--install)
        install_prefix=$2
        shift
        shift
        ;;
        -l|--local|--prefer-local)
        prefer_local_deps=1
        shift
        ;;
        *)    # everything else
        cmake_args="$cmake_args $arg" # unknown args are passed to cmake
        shift
        ;;
    esac
done

if [ $clean ]; then
    rm -rf $deps_dir
fi
mkdir -p $deps_dir

install_dep aws-c-common
install_dep aws-c-io
install_dep aws-c-mqtt
