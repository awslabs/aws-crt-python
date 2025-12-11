from awscrt.cbor import *
import random
import time
import cbor2


# TypedCborEncoder mimics CrtRpcV2CBORSerializer behavior:
# Instead of using write_data_item(), it inspects types and calls specific write_<type> methods
class TypedCborEncoder:
    """
    Custom encoder that mimics CrtRpcV2CBORSerializer's approach.
    Instead of using the generic write_data_item(), it inspects Python types
    and calls the appropriate write_<type>() methods on AwsCborEncoder.
    """

    def __init__(self):
        self.encoder = AwsCborEncoder()

    def encode(self, data):
        """Encode data by inspecting types and using specific write methods."""
        self._encode_value(data)
        return self.encoder.get_encoded_data()

    def _encode_value(self, value):
        """Recursively encode a value based on its type."""
        if value is None:
            self.encoder.write_null()
        elif isinstance(value, bool):
            self.encoder.write_bool(value)
        elif isinstance(value, int):
            self.encoder.write_int(value)
        elif isinstance(value, float):
            self.encoder.write_float(value)
        elif isinstance(value, str):
            self.encoder.write_text(value)
        elif isinstance(value, bytes):
            self.encoder.write_bytes(value)
        elif isinstance(value, dict):
            self._encode_map(value)
        elif isinstance(value, (list, tuple)):
            self._encode_array(value)
        else:
            raise TypeError(f"Unsupported type: {type(value)}")

    def _encode_map(self, data):
        """Encode a dictionary as a CBOR map."""
        self.encoder.write_map_start(len(data))
        for key, value in data.items():
            # Encode the key (typically a string)
            self._encode_value(key)
            # Encode the value
            self._encode_value(value)

    def _encode_array(self, data):
        """Encode a list/tuple as a CBOR array."""
        self.encoder.write_array_start(len(data))
        for item in data:
            self._encode_value(item)


# Verify cbor2 is using C extension for fair comparison
try:
    from cbor2 import _decoder
    print(f"✅ cbor2 C extension: {_decoder}")
except ImportError:
    print("⚠️  WARNING: cbor2 C extension not available - using pure Python implementation")
    print("   Install with: pip install cbor2[c]")

print()


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


# print(t)

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


print("CRT -- encode (verify)")
encoder_2 = AwsCborEncoder()
run_start_ns = time.perf_counter_ns()
encoder_2.write_data_item(t)
encoded_2 = encoder_2.get_encoded_data()
run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"encoded MB: {bytes_to_MiB(len(encoded_2))}")
print(f"time passed: {run_secs} secs")


print(f"cbor2 == CRT encode: {cbor2_encoded == encoded}")
print(f"CRT encode == CRT encode verify: {encoded == encoded_2}")

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


print("CRT -- decode (verify)")
run_start_ns = time.perf_counter_ns()
decoder_2 = AwsCborDecoder(encoded)
crt_decoded_2 = decoder_2.pop_next_data_item()

run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"time passed: {run_secs} secs")

print(f"CRT decoded == original data: {crt_decoded == t}")
print(f"CRT decoded verify == original data: {crt_decoded_2 == t}")


print("\n--- TypedCborEncoder Benchmark ---")
print("TypedCborEncoder -- encode (type-aware write_<type> calls)")

# Create encoder and benchmark
typed_encoder = TypedCborEncoder()
run_start_ns = time.perf_counter_ns()
typed_encoded = typed_encoder.encode(t)
run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"encoded MB: {bytes_to_MiB(len(typed_encoded))}")
print(f"time passed: {run_secs} secs")


print("TypedCborEncoder -- encode (verify)")
typed_encoder_2 = TypedCborEncoder()
run_start_ns = time.perf_counter_ns()
typed_encoded_2 = typed_encoder_2.encode(t)
run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"encoded MB: {bytes_to_MiB(len(typed_encoded_2))}")
print(f"time passed: {run_secs} secs")

print(f"TypedCborEncoder encode == CRT encode: {typed_encoded == encoded}")
print(f"TypedCborEncoder encode == verify: {typed_encoded == typed_encoded_2}")

# Decode with CRT decoder to verify correctness
print("\nCRT -- decode TypedCborEncoder output")
run_start_ns = time.perf_counter_ns()
decoder_typed = AwsCborDecoder(typed_encoded)
typed_decoded = decoder_typed.pop_next_data_item()
run_secs = ns_to_secs(time.perf_counter_ns() - run_start_ns)
print(f"time passed: {run_secs} secs")
print(f"TypedCborEncoder decoded == original data: {typed_decoded == t}")
