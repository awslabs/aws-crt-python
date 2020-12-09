# get_object()
#    |
#     ---> Validate, serliaze HTTP request
#                                         ---> Sign request
#                                                          --> HTTP request
#                                                          <-- HTTP response
#   {}  Parse the response <------------------------------
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
# import urlparse

s = botocore.session.Session()
config = Config(signature_version=UNSIGNED)
s3 = s.create_client('s3', region_name="us-west-2", config=config)

# s.set_debug_logger()


class FakeRawResponse(six.BytesIO):
    def stream(self, amt=1024, decode_content=None):
        while True:
            chunk = self.read(amt)
            if not chunk:
                break
            yield chunk


def crt_client_init(request):
    crt_request = CrtUtil.crt_request_from_aws_request(request)
    if crt_request.headers.get("host") is None:
        # If host is not set, set it for the request before using CRT s3
        url_parts = urlsplit(request.url)
        crt_request.headers.set("host", url_parts.netloc)
    event_loop_group = EventLoopGroup()
    host_resolver = DefaultHostResolver(event_loop_group)
    bootstrap = ClientBootstrap(event_loop_group, host_resolver)
    credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
    # TODO: The region in the request will still be the same as the region in the configuration.
    # Not sure what will be affected by the region of the crt S3 client.
    s3_client = S3Client(
        bootstrap=bootstrap,
        region="us-west-2",
        credential_provider=credential_provider,
        part_size=5 * 1024 * 1024)
    return crt_request, s3_client


def crt_get_object(request, **kwargs):
    print(request)
    crt_request, s3_client = crt_client_init(request=request)
    file = open("get_object_test_1MB.txt", "wb")

    def on_response_body(chunk, **kwargs):
        print("something")
        file.write(chunk)

    init_logging(LogLevel.Trace, "log.txt")
    code = 0
    headers_dict = {}

    def on_response_headers(status_code, headers, **kwargs):
        nonlocal code
        code = status_code
        nonlocal headers_dict
        headers_dict = dict(headers)

    body = FakeRawResponse(b"")
    s3_request = s3_client.make_request(
        request=crt_request,
        type=AwsS3RequestType.GET_OBJECT,
        on_headers=on_response_headers,
        on_body=on_response_body)
    finished_future = s3_request.finished_future
    result = finished_future.result(1000)
    file.close()
    response = botocore.awsrequest.AWSResponse("none", code, headers_dict, body)

    return response


def crt_put_object(request, **kwargs):
    print(request)
    crt_request, s3_client = crt_client_init(request=request)
    # content-md5 is not supported by CRT yet, and will be not supported in
    # the near future, will be stripped out by native client later
    crt_request.headers.remove('content-md5')
    code = 0
    headers_dict = {}

    def on_response_headers(status_code, headers, **kwargs):
        nonlocal code
        code = status_code
        nonlocal headers_dict
        headers_dict = dict(headers)

    body = FakeRawResponse(b"")
    s3_request = s3_client.make_request(
        request=crt_request,
        type=AwsS3RequestType.PUT_OBJECT,
        on_headers=on_response_headers)
    finished_future = s3_request.finished_future
    result = finished_future.result(1000)
    response = botocore.awsrequest.AWSResponse("none", code, headers_dict, body)

    return response


s3.meta.events.register('before-send.s3.GetObject', crt_get_object)
s3.meta.events.register('before-send.s3.PutObject', crt_put_object)

data_stream = open("put_object_test_10MB.txt", 'rb')

(s3.put_object(
    Body=data_stream,
    Bucket='aws-crt-canary-bucket',
    Key='put_object_test_py_10MB.txt'
))

(s3.get_object(
    Bucket='aws-crt-canary-bucket',
    Key='put_object_test_py_10MB.txt'
))
