# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import boto3
import base64
import os
import argparse


def get_secret(stage):

    secret_name = '{}/aws-crt-python/.pypirc'.format(stage)
    region_name = 'us-east-1'

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    secret = None
    get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    # Decrypts secret using the associated KMS CMK.
    # Depending on whether the secret is a string or binary, one of these fields will be populated.
    if 'SecretString' in get_secret_value_response:
        secret = get_secret_value_response['SecretString']
    else:
        decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
        secret = decoded_binary_secret

    with open(os.path.join(os.path.expanduser('~/'), '.pypirc'), 'w') as f:
        f.write(secret)

    print('.pypirc written to {}'.format(os.path.join(os.path.expanduser('~/'), '.pypirc')))

parser = argparse.ArgumentParser()
parser.add_argument('stage', help='Stage to deploy the pypi package to (e.g. alpha, prod, etc...)', type=str)
args = parser.parse_args()
get_secret(args.stage)

