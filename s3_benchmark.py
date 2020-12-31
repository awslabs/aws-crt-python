from awscrt.s3 import S3Client, S3RequestType
from awscrt.io import ClientBootstrap, DefaultHostResolver, EventLoopGroup
from awscrt.auth import AwsCredentialsProvider
from awscrt.http import HttpHeaders, HttpRequest
import time
# import os
import sys
import threading
import csv

GBPS = 1000 * 1000 * 1000


class CrtLazyReadStream(object):
    def __init__(self, filename, pattern, statistics, length=0):
        self._filename = filename
        self.length = length
        self._stream = None
        self._pattern = pattern
        self._statistic = statistics

    def _available_stream(self):
        if self._stream is None:
            self._stream = open(self._filename, self._pattern)
            return

        if self._stream.closed:
            self._stream = open(self._filename, self._pattern)

    def read(self, length):
        self._available_stream()
        data = self._stream.read(length)
        read_len = len(data)
        self._statistic.record_read(read_len)
        if read_len is 0:
            self._stream.close()
        return data

    def readinto1(self, m):
        # Read into memoryview m.
        self._available_stream()
        len = self._stream.readinto1(m)
        self._statistic.record_read(len)
        if len is 0:
            self._stream.close()
        return len

    def seek(self, offset, whence):
        self._available_stream()
        return self._stream.seek(offset, whence)

    def close(self):
        pass


class Statistics(object):

    def __init__(self):
        self._lock = threading.Lock()
        self.end_time = 0
        self._bytes_peak = 0
        self._bytes_avg = 0
        self._bytes_read = 0
        self._bytes_sampled = 0
        self.sec_first_byte = 0
        self.star_time = time.time()
        self.last_sample_time = time.time()
        self.all_data = []

    def record_read(self, size):
        with self._lock:
            self._bytes_read += size
            if self.sec_first_byte == 0:
                self.sec_first_byte = time.time() - self.star_time
            time_now = time.time()
            if time_now - self.last_sample_time > 1:
                bytes_this_second = (self._bytes_read - self._bytes_sampled) / (time_now - self.last_sample_time)
                self._bytes_sampled = self._bytes_read
                self._bytes_avg = (self._bytes_avg + bytes_this_second) * 0.5
                self.all_data.append((bytes_this_second * 8) / GBPS)
                if self._bytes_peak < bytes_this_second:
                    self._bytes_peak = bytes_this_second
                self.last_sample_time = time_now

    def bytes_peak(self):
        return (self._bytes_peak * 8) / GBPS

    def bytes_avg(self):
        return (self._bytes_avg * 8) / GBPS


# Configurations
region = "us-west-2"
bucket_name = "aws-crt-python-s3-testing-bucket"
object_name = "/0_10GB.txt"
file_name = "." + object_name
object_real_name = "/0_10GB"
suffix = ".txt"
repeat_times = 160
bunch_size = 1

writing_disk = True
request_type = "download"

# Initialization
event_loop_group = EventLoopGroup(18)
host_resolver = DefaultHostResolver(event_loop_group)
bootstrap = ClientBootstrap(event_loop_group, host_resolver)
credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
s3_client = S3Client(
    bootstrap=bootstrap,
    region="us-west-2",
    credential_provider=credential_provider,
    throughput_target_gbps=100)

t_statistic = Statistics()

headers = HttpHeaders([("host", bucket_name + ".s3." + region + ".amazonaws.com")])
request = HttpRequest("GET", object_name, headers)

# file_stats = os.stat(file_name)
# data_len = file_stats.st_size

# data_stream = CrtLazyReadStream(file_name, "r+b", t_statistic, data_len)
# upload_headers = HttpHeaders([("host", bucket_name + ".s3." + region + ".amazonaws.com"),
#                               ("Content-Type", "text/plain"), ("Content-Length", str(data_len))])
# upload_request = HttpRequest("PUT", "/put_object_test_py_10MB.txt", upload_headers, data_stream)


def on_body(offset, chunk, **kwargs):

    # pass
    # print(kwargs)
    t_statistic.record_read(kwargs['size'])
    # if writing_disk:
    #     if not os.path.exists(file_name):
    #         open(file_name, 'a').close()
    #     with open(file_name, 'rb+') as f:
    #         # seems like the seek here may srew up the file.
    #         f.seek(offset)
    #         f.write(chunk)


completed_connections = 0


def on_done(**kwargs):
    global completed_connections
    completed_connections += 1
    print("Finished connection {}".format(completed_connections))
    sys.stdout.flush()


def print_statistic(statistic):
    print("Gbps peak:", statistic.bytes_peak())
    print("Gbps avg:", statistic.bytes_avg())
    sys.stdout.flush()


# init_logging(LogLevel.Trace, "trace_log.txt")
start_time = time.time()
completed = repeat_times * bunch_size


for i in range(0, repeat_times):
    print(i)
    # futures = []
    # s3_requests = []
    file = "/dev/null"
    for j in range(0, bunch_size):

        s3_request = (s3_client.make_request(
            request=request,
            type=S3RequestType.GET_OBJECT,
            file=file,
            on_body=on_body,
            on_done=on_done))

        try:
            s3_request.finished_future.result(10000)
        except Exception as e:
            completed = completed - 1

    # file.close()
    # print_statistic(t_statistic)

end_time = time.time()
print_statistic(t_statistic)

# with open('result.csv', 'w') as csvfile:
#     spamwriter = csv.writer(csvfile,
#                             quotechar='|', quoting=csv.QUOTE_MINIMAL)
#     spamwriter.writerow(t_statistic.all_data)


print("total time:", end_time - start_time)
print("completed/all:", completed, repeat_times * bunch_size)
print("latency:", t_statistic.sec_first_byte)
# file.close()
