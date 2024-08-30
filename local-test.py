import logging
from awscrt import io
from botocore.auth import *
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from botocore.session import get_session
from botocore.crt.auth import *

# Set up logging to capture trace-level logs
logging.basicConfig()
logging.getLogger('botocore').setLevel(logging.DEBUG)

io.init_logging(io.LogLevel.Trace, 'stderr')


def presign_post_request(
        service_name,
        region_name,
        endpoint,
        request_parameters,
        access_key,
        secret_key,
        session_token=None):
    # Create a session and get credentials
    session = get_session()

    # Create credentials object
    credentials = Credentials(access_key, secret_key, session_token)

    # Create the AWSRequest object
    request = AWSRequest(
        method="POST",
        url=endpoint,
        data=request_parameters,
        headers={
            "Host": "example.amazonaws.com",
            'Content-Type': 'application/json',
            "x-amz-content-sha256": "UNSIGNED-PAYLOAD",
            'Content-Length': '123',
        }
    )
    # request.context["payload_signing_enabled"] = False

    # Sign the request using SigV4QueryAuth
    # SigV4QueryAuth(credentials, service_name, region_name).add_auth(request)
    CrtSigV4AsymQueryAuth(credentials, service_name, region_name).add_auth(request)

    # The presigned URL is now in request.url
    signed_request = request
    return signed_request


# Example usage
service_name = 'vpc-lattice-svcs'
region_name = 'us-west-2'
endpoint = 'https://example.amazonaws.com/'
request_parameters = '{\
    "Param1": "value1"\
}'
access_key = 'your-access-key'
secret_key = 'your-secret-key'
session_token = None  # If using temporary credentials

signed_request = presign_post_request(
    service_name, region_name, endpoint, request_parameters, access_key, secret_key, session_token)

print("Presigned URL:", signed_request.url)
print("Headers:", signed_request.headers)
print("Params:", signed_request.params)

signed_request.prepare()
