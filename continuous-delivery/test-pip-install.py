# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt.s3

print('if the next statement does not explode, the pip install was successful')
print('Is on Ec2 Instance nitro ? {}', awscrt.s3.is_running_on_ec2_nitro())
print('Instance Type = {}', awscrt.s3.is_running_on_ec2_nitro())
print('Is Optimized for System = {}', awscrt.s3.is_optimized_for_system())
