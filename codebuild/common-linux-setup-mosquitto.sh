#!/bin/bash

set -e

# Make a directory to install all of the mosquitto stuff into
mkdir -p MosquittoInstall
cd MosquittoInstall

# mosquitto needs OpenSSL at version 1.1.0+, so we have to install from source
echo "Setup mosquitto dependencies from source - OpenSSL (may take a couple minutes - should take no more than 6 minutes)"
# Note: 99% of the time we do not care for the output, so let's hide it to reduce console spam!
{
    git clone https://github.com/openssl/openssl.git --branch OpenSSL_1_1_1s
    cd openssl
    ./config --prefix=/usr/local --openssldir=/usr/local
    make
    sudo make install
} > /dev/null

# We have to install libwebsockets from source for mosquitto too for websockets support
# Note: 99% of the time we do not care for the output, so let's hide it to reduce console spam!
echo "Setup mosquitto dependencies from source - LibWebsockets (may take a couple minutes - should take no more than 6 minutes)"
{
    git clone https://github.com/warmcat/libwebsockets.git --branch v4.3.2
    cd libwebsockets
    mkdir build
    cd build
    cmake .. -DLWS_WITH_EXTERNAL_POLL=ON
    make
    sudo make install
cd ../..
} > /dev/null

# Install mosquitto from source (apt-get version is too old)
# Note: 99% of the time we do not care for the output, so let's hide it to reduce console spam!
echo "Setup mosquitto from source - Mosquitto (may take a couple minutes - should take no more than 6 minutes)"
{
    git clone https://github.com/eclipse/mosquitto.git --branch v2.0.15
    cd mosquitto
    make install WITH_DOCS=no WITH_CJSON=no WITH_WEBSOCKETS=yes LDFLAGS="-L/usr/local/lib/  -Wl,-rpath,/usr/local/lib/"
    cd ..
    sudo ldconfig
} > /dev/null

# Get the Mosquttio config file and run it
echo "Setup mosquitto from source - configure mosquitto and start it running"
aws s3 cp s3://aws-crt-test-stuff/setup_mosquitto_test_env.sh ./setup_mosquitto_test_env.sh
sudo chmod a+xr ./setup_mosquitto_test_env.sh
./setup_mosquitto_test_env.sh
mosquitto -d -c /etc/mosquitto/mosquitto.conf

# Done!
cd ..
