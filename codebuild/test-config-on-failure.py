# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import awscrt

print('Is CRT wheel installed? {}', awscrt.crt_wheel_installed())
## this had better be False since the caller sabotaged the build in some way.
assert(awscrt.crt_wheel_installed() == False)
