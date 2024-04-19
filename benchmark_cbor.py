from awscrt.cbor import *
import random
import time
import cbor2


def ns_to_secs(ns: int) -> float:
    return ns / 1_000_000_000.0


def bytes_to_MiB(bytes: int) -> float:
    return bytes / float(1024**2)


class TestData:
    # generate predictable, but variable test values of different types
    @staticmethod
    def random_value(i=0, seed=0):
        r = random.Random(i + seed)  # use the index as the seed for predictable results
        random_number = TestData.random_number(r, 5)
        if random_number == 0:
            return f"Some String value {i}"
        elif random_number == 1:
            return r.random()  # a float value
        elif random_number == 2:
            return TestData.random_number(r, 100000)  # a large integer
        elif random_number == 3:
            return list(range(TestData.random_number(r, 100)))  # an array
        elif random_number == 4:
            return {"a": 1, "b": 2, "c": 3}  # a hash
        else:
            return "generic string"

    # generate a predictable, but variable hash with a range of data types
    @staticmethod
    def test_hash(n_keys=5, seed=0):
        return {f"key{i}": TestData.random_value(i, seed) for i in range(n_keys)}

    @staticmethod
    def random_number(r, n):
        return int(r.random() * n)


t = TestData.test_hash(100000)


print("cbor2 -- encode")
run_start_ns = time.perf_counter_ns()
cbor2_encoded = cbor2.dumps(t)
run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"encoded MB: {bytes_to_MiB(len(cbor2_encoded))}")
print(f"time passed: {run_secs} secs")


print("CRT -- encode")
encoder = AwsCborEncoder()

run_start_ns = time.perf_counter_ns()
encoder.write_data_item(t)
encoded = encoder.get_encoded_data()
run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"encoded MB: {bytes_to_MiB(len(encoded))}")
print(f"time passed: {run_secs} secs")

print(cbor2_encoded == encoded)

print("cbor2 -- decode")
run_start_ns = time.perf_counter_ns()
decoded = cbor2.loads(encoded)
run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"time passed: {run_secs} secs")

print("CRT -- decode")
run_start_ns = time.perf_counter_ns()
decoder = AwsCborDecoder(encoded)
crt_decoded = decoder.pop_next_data_item()

run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"time passed: {run_secs} secs")


print("CRT -- decode 2")
run_start_ns = time.perf_counter_ns()
decoder_2 = AwsCborDecoder(encoded)
decoder_2.consume_next_data_item()

run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"time passed: {run_secs} secs")

print(crt_decoded == t)
print(crt_decoded == decoded)
