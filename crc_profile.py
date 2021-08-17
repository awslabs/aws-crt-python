#!/usr/bin/env python

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import os
import time
import zlib
from awscrt import checksums


# Welfords online algorithm
def update_summary(count, mean, M2, my_min, my_max, new_value):
    delta = new_value - mean
    mean += delta / count
    delta2 = new_value - mean
    M2 += delta * delta2
    my_min = min(my_min, new_value)
    my_max = max(my_max, new_value)
    return {"mean": mean, "M2": M2, "min": my_min, "max": my_max}


def finalize_summary(count, M2):
    return M2 / count

# mean, variance, min, max, chunk_size, num_chunks


def print_stats(stats):
    for s in stats:
        print('chunk size: {chunk_size}, min: {min}, max: {max}, mean: {mean}, variance: {variance}'.format(**s))


def profile_sequence_chunks(to_hash, chunk_size, iterations, checksum_fn):
    stats = {"mean": 0, "M2": 0, "min": float('inf'), "max": 0}
    dif = 0
    for x in range(iterations):
        i = 0
        prev = 0
        start = time.time_ns()
        while(i + chunk_size < len(to_hash)):
            prev = checksum_fn(to_hash[i:i + chunk_size], prev)
            i = i + chunk_size
        prev = checksum_fn(to_hash[i:], prev)
        end = time.time_ns()
        stats = update_summary(x + 1, *stats.values(), end - start)
    return stats["mean"]


def profile_sequence(to_hash, chunk_sizes, iterations_per_sequence, checksum_fn):
    times = []
    for size in chunk_sizes:
        toss = profile_sequence_chunks(to_hash, size, iterations_per_sequence, checksum_fn)
        times.append(profile_sequence_chunks(to_hash, size, iterations_per_sequence, checksum_fn))
    return times


def profile(size, chunk_sizes, num_sequences, iterations_per_sequence, checksum_fn):
    stats = [{"mean": 0, "M2": 0, "min": float('inf'), "max": 0} for x in [None] * len(chunk_sizes)]
    for x in range(num_sequences):
        buffer = os.urandom(size)
        if(x % 100 == 0):
            print(f'count: {x}')
        stats = [
            update_summary(
                x + 1,
                *stat.values(),
                time) for stat,
            time in zip(
                stats,
                profile_sequence(
                    buffer,
                    chunk_sizes,
                    iterations_per_sequence,
                    checksum_fn))]
    for (stat, chunk) in zip(stats, chunk_sizes):
        stat["variance"] = finalize_summary(num_sequences, stat["M2"])
        stat["chunk_size"] = chunk
    print_stats(stats)


chunks = [2 ** x for x in range(22, 6, -1)]
print("Python crc32")
profile(2 ** 22, chunks, 1000, 1, checksums.crc32)
print("Python crc32c")
profile(2 ** 22, chunks, 1000, 1, checksums.crc32c)
print("Python zlib crc32")
profile(2 ** 22, chunks, 1000, 1, zlib.crc32)
