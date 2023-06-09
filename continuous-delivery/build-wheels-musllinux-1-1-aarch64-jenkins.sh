#!/bin/bash
#run build-wheels script in musllinux_1_1 docker image
set -ex

DOCKER_IMAGE=123124136734.dkr.ecr.us-east-1.amazonaws.com/aws-crt-musllinux-1-1-aarch64:latest

$(aws --region us-east-1 ecr get-login --no-include-email)

docker pull $DOCKER_IMAGE

# NOTE: run as current user to avoid git "dubious ownership" error,
# and so that output artifacts don't belong to "root"
docker run --rm \
    --mount type=bind,source=`pwd`,target=/aws-crt-python \
    --user "$(id -u):$(id -g)" \
    --workdir /aws-crt-python \
    --entrypoint /bin/bash \
    $DOCKER_IMAGE \
    continuous-delivery/build-wheels-musllinux-1-1-aarch64.sh
