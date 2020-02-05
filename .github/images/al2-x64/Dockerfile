FROM amazonlinux:latest

SHELL ["/bin/bash", "-c"]

###############################################################################
# Install prereqs
###############################################################################
RUN yum -y update

RUN yum -y install \
    git \
    curl \
    sudo \
    # Python
    python3 \
    python3-devel \
    python3-pip \
    make \
    cmake3 \
    gcc \
    gcc-c++

###############################################################################
# Python/AWS CLI
###############################################################################
RUN python3 -m pip install --upgrade pip setuptools virtualenv \
    && python3 -m pip install --upgrade awscli \
    && aws --version

###############################################################################
# OpenSSL
###############################################################################
RUN set -ex \
    && ([ -d /opt/openssl ] && rm -rf /opt/openssl) || true \
    && mkdir -p /tmp/build \
    && cd /tmp/build \
    && git clone https://github.com/openssl/openssl.git \
    && pushd openssl \
    && git checkout OpenSSL_1_1_1-stable \
    && ./config -fPIC \
        no-md2 no-rc5 no-rfc3779 no-sctp no-ssl-trace no-zlib no-hw no-mdc2 \
        no-seed no-idea no-camellia no-bf no-dsa no-ssl3 no-capieng \
        no-unit-test no-tests \
        -DSSL_FORBID_ENULL -DOPENSSL_NO_DTLS1 -DOPENSSL_NO_HEARTBEATS \
        --prefix=/opt/openssl --openssldir=/opt/openssl \
    && make -j \
    && make install_sw \
    && LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/openssl/lib /opt/openssl/bin/openssl version

###############################################################################
# Cleanup
###############################################################################
RUN set -ex \
    && yum clean all \
    && rm -rf /tmp/*
