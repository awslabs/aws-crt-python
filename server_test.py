# Copyright 2010-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

import argparse
import sys
import os
from io import BytesIO
from awscrt import io, http

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', required=False, help='ERROR|INFO|DEBUG|TRACE: log level to configure. Default is none.')
parser.add_argument('-t', '--trace', required=False, help='FILE: dumps logs to FILE instead of stderr.')

args = parser.parse_args()
# setup the logger if user request logging

if args.verbose:
    log_level = io.LogLevel.NoLogs

    if args.verbose == 'ERROR':
        log_level = io.LogLevel.Error
    elif args.verbose == 'INFO':
        log_level = io.LogLevel.Info
    elif args.verbose == 'DEBUG':
        log_level = io.LogLevel.Debug
    elif args.verbose == 'TRACE':
        log_level = io.LogLevel.Trace
    else:
        print('{} unsupported value for the verbose option'.format(args.verbose))
        exit(-1)

    log_output = 'stderr'

    if args.trace:
        log_output = args.trace

    io.init_logging(log_level, log_output)

# an event loop group is needed for IO operations. Unless you're a server or a client doing hundreds of connections
# you only want one of these.
event_loop_group = io.EventLoopGroup(1)

# server bootstrap init
with io.ServerBoostrap(event_loop_group) as server_boostrap:
    print('create server boostrap succeed')
