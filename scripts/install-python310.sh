#!/bin/bash
set -e

# Install Python 3.10 on Ubuntu 18.04
apt-get update
apt-get install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y python3.10 python3.10-venv python3.10-dev

# Create symlink for python3.10 if it doesn't exist
if [ ! -f /usr/bin/python3.10 ]; then
    ln -sf /usr/bin/python3.10 /usr/bin/python3.10
fi