import requests
import time
import datetime
import hashlib
import sys, os, base64, hmac
from requests_aws4auth import AWS4Auth

    

if __name__ == "__main__":
    access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    session_token = os.environ.get('AWS_SESSION_TOKEN')
    #request type, host and header info
    host_name = "crt-canary-bucket-ramosth.s3.us-east-2.amazonaws.com"
    region = "us-east-2"
    service = "s3"
    method = "GET"
    request_parameters = ""
    #bucket_name = "crt-canary-bucket-ramosth-"
    key = "crt-canary-obj-single-part-"
    obj_num = 9223372036854775806
    #url = "https://s3.amazonaws.com/crt-canary-bucket-ramosth"
    endpoint = "http://crt-canary-bucket-ramosth.s3.us-east-2.amazonaws.com"
    numTransfers = 1
    

    start = time.time()
    for i in range(numTransfers):
        obj_key = "/" + key + str(obj_num)
        obj_num -= 1

        auth = AWS4Auth(access_key_id, secret_access_key, region, service, session_token=session_token)
        print("start request")
        response = requests.get(endpoint + obj_key, auth=auth)
        print(response.status_code, "\n")
        #print(response.text)
    end = time.time()
    total = end - start
    print("Time to complete in seconds: ", total)