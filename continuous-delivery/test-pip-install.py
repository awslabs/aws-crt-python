# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt.io

print('if the next statement does not explode, the pip install was successful') 
print('Is alpn supported? {}', awscrt.io.is_alpn_available())
