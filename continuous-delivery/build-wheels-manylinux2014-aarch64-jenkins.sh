#!/bin/bash
#run build-wheels script in manylinux2014 docker image
set -ex

DOCKER_IMAGE=123124136734.dkr.ecr.us-east-1.amazonaws.com/aws-crt/manylinux2014-aarch64:latest

$(aws --region us-east-1 ecr get-login --no-include-email)

docker pull $DOCKER_IMAGE

docker run --rm \
    --mount type=bind,source=`pwd`,target=/aws-crt-python \
    --workdir /aws-crt-python \
    --entrypoint /bin/bash \
    $DOCKER_IMAGE \
    continuous-delivery/build-wheels-manylinux2014-aarch64.sh
