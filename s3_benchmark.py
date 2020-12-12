import io
from botocore import args
import botocore.awsrequest
import botocore.session
from botocore.utils import CrtUtil
from botocore import UNSIGNED
from botocore.config import Config
from botocore.compat import urlsplit, six
from awscrt.s3 import S3Client, AwsS3RequestType
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, init_logging, LogLevel
from awscrt.auth import AwsCredentialsProvider
from awscrt.http import HttpHeaders, HttpRequest
from urllib3.response import HTTPResponse
import time
import os

GBPS = 1000 * 1000 * 1000


class CrtLazyReadStream(object):
    def __init__(self, filename, pattern, statistics, length=0):
        self._filename = filename
        self.length = length
        self._stream = None
        self._pattern = pattern
        # self._subscriber_manager = subscriber_manager
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
        self.end_time = 0
        self._bytes_peak = 0
        self._bytes_avg = 0
        self._bytes_read = 0
        self._bytes_sampled = 0
        self.sec_first_byte = 0
        self.star_time = time.time()
        self.last_sample_time = time.time()

    def record_read(self, size):
        self._bytes_read+=size
        do_print = False
        if self.sec_first_byte == 0:
            self.sec_first_byte = time.time() - self.star_time
            do_print = True
        time_now = time.time()
        if time_now - self.last_sample_time > 1:
            bytes_this_second = (self._bytes_read-self._bytes_sampled)/(time_now - self.last_sample_time)
            self._bytes_sampled = self._bytes_read
            self._bytes_avg = (self._bytes_avg+bytes_this_second)*0.5
            if self._bytes_peak < bytes_this_second:
                self._bytes_peak = bytes_this_second
            self.last_sample_time = time_now

    def bytes_peak(self):
        return (self._bytes_peak*8)/GBPS

    def bytes_avg(self):
        return (self._bytes_avg*8)/GBPS

event_loop_group = EventLoopGroup()
host_resolver = DefaultHostResolver(event_loop_group)
bootstrap = ClientBootstrap(event_loop_group, host_resolver)
credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
s3_client = S3Client(
    bootstrap=bootstrap,
    region="us-west-2",
    credential_provider=credential_provider,
    throughput_target_gbps=100)

region = "us-west-2"
bucket_name = "aws-crt-python-s3-testing-bucket"
object_name= "/0_10GB.txt"
# s3://aws-crt-python-s3-testing-bucket/0_10GB.txt
file_name = "." + object_name
object_real_name = "/0_10GB"
suffix = ".txt"
download_times = 20
bunch_size = 1


t_statistic = Statistics()

headers = HttpHeaders([("host", bucket_name + ".s3." + region + ".amazonaws.com")])
request = HttpRequest("GET", object_name, headers)

# file_stats = os.stat(file_name)
# data_len = file_stats.st_size
# print(data_len)

# data_stream = CrtLazyReadStream(file_name, "r+b", t_statistic, data_len)
# data_stream = open(file_name, 'rb')
# upload_headers = HttpHeaders([("host", bucket_name + ".s3." + region + ".amazonaws.com"), ("Content-Type", "text/plain"), ("Content-Length", str(data_len))])
# upload_request = HttpRequest("PUT", "/put_object_test_py_10MB.txt", upload_headers, data_stream)


def on_body(offset, chunk, **kwargs):
    t_statistic.record_read(len(chunk))
    # if not os.path.exists(file_name):
    #     open(file_name, 'a').close()
    # with open(file_name, 'rb+') as f:
    #     # seems like the seek here may srew up the file.
    #     f.seek(offset)
    #     f.write(chunk)

def on_headers(status_code, headers):
    """
    check the status and probably print out the headers
    """
    print(status_code)
    print(headers)

def print_statistic(statistic):
    print("Gbps peak:", statistic.bytes_peak())
    print("Gbps avg:", statistic.bytes_avg())


# init_logging(LogLevel.Trace, "trace_log.txt")
start_time = time.time()
completed = download_times * bunch_size

# s3_request = s3_client.make_request(
#     request=upload_request,
#     type=AwsS3RequestType.PUT_OBJECT,
#     on_headers=on_headers
# )
# finished_future = s3_request.finished_future
# try:
#     result = finished_future.result(100)
# except Exception as e:
#     print("request finished with failure:", e)
for i in range(0, download_times):
    futures = []
    s3_requests = []
    key = "/0_10GB_"+str(i)+suffix
    request = HttpRequest("GET", key, headers)
    # data_stream = CrtLazyReadStream(file_name, "rb", t_statistic, data_len)
    # upload_request = HttpRequest("PUT", object_real_name+str(i)+suffix, upload_headers, data_stream)
    for j in range(0,bunch_size):
        s3_requests.append(s3_client.make_request(
            request=request,
            type=AwsS3RequestType.GET_OBJECT,
            on_body=on_body))
        # s3_requests.append(s3_client.make_request(
        #     request=upload_request,
        #     type=AwsS3RequestType.PUT_OBJECT))
        futures.append(s3_requests[j].finished_future)
    for j in futures:
        try:
            j.result(100000)
        except:
            # print(sys.exc_info()[0])
            completed = completed-1
    # print_statistic(t_statistic)



end_time = time.time()
print_statistic(t_statistic)
print("total time:", end_time-start_time)
print("completed/all:", completed, download_times* bunch_size)
print("lentency:", t_statistic.sec_first_byte)
