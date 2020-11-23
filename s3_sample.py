from awscrt.s3 import S3Client, AwsS3RequestType
from awscrt.io import ClientBootstrap, ClientTlsContext, DefaultHostResolver, EventLoopGroup, TlsConnectionOptions, TlsContextOptions, init_logging, LogLevel
from awscrt.auth import AwsCredentialsProvider
from awscrt.http import HttpHeaders, HttpRequest
from pycallgraph import PyCallGraph
from pycallgraph.output import GraphvizOutput

with PyCallGraph(output=GraphvizOutput()):
    event_loop_group = EventLoopGroup()
    host_resolver = DefaultHostResolver(event_loop_group)
    bootstrap = ClientBootstrap(event_loop_group, host_resolver)
    credential_provider = AwsCredentialsProvider.new_default_chain(bootstrap)
    s3_client = S3Client(
        bootstrap=bootstrap,
        region="us-west-2",
        credential_provider=credential_provider)
    headers = HttpHeaders([("host", "aws-crt-canary-bucket" + ".s3." + "us-west-2" + ".amazonaws.com")])
    request = HttpRequest("GET", "/crt-canary-obj-single-part-9223372036854775807", headers)
    file = open("5GB.txt", "wb")

    def on_body(chunk):
        file.write(chunk)

    s3_request = s3_client.make_request(
        request=request,
        type=AwsS3RequestType.GET_OBJECT,
        on_body=on_body)
    finished_future = s3_request.finished_future
    result = finished_future.result(10000)
    file.close()

    print("done!")
