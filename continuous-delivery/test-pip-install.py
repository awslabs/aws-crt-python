# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt.s3

print("if the next statement does not explode, the pip install was successful")
print(f"Instance Type = {awscrt.s3.get_ec2_instance_type()}")
print(f"Is Optimized for System = {awscrt.s3.is_optimized_for_system()}")
