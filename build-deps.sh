#!/usr/bin/env bash

# usage:
# ./build-deps.sh
#   -c, --clean - remove any cached CMake config before building
#   -i, --install <path> - sets the CMAKE_INSTALL_PREFIX, the root where the deps will be install
#   <all other args> - will be passed to cmake as-is

# assumes that the dependency git repos are cloned in the parent
# folder, next to this project
deps=(aws-c-common aws-c-io aws-c-mqtt)

# everything is relative to the directory this script is in
home_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

# where to have cmake put its binaries
deps_dir=$home_dir/build/deps

install_prefix=$deps_dir/install

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
        *)    # everything else
        cmake_args="$cmake_args $arg" # unknown args are passed to cmake
        shift
        ;;
    esac
done

if [ $clean ]; then
    rm -r $deps_dir
fi
mkdir -p $deps_dir

for dep in ${deps[@]}; do
    # build
    src_dir=$home_dir/../$dep
    dep_dir=$deps_dir/$dep
    mkdir -p $dep_dir
    pushd $dep_dir

    echo "cmake -GNinja $cmake_args -DCMAKE_INSTALL_PREFIX=$install_prefix $src_dir"
    cmake -GNinja $cmake_args -DCMAKE_INSTALL_PREFIX=$install_prefix $src_dir
    cmake --build . --target all
    cmake --build . --target install

    popd
done
