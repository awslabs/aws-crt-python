#!/bin/bash
#run build-wheels script in manylinux2014 docker image
set -ex

DOCKER_IMAGE=123124136734.dkr.ecr.us-east-1.amazonaws.com/aws-crt-manylinux2014-x64:latest

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
    continuous-delivery/build-wheels-manylinux2014-x86_64.sh
