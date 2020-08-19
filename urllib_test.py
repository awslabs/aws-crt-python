import urllib3
import os
import time
import datetime
import io
from requests_aws4auth import AWS4Auth
import argparse
import threading
import requests
import sys
import asyncio

#def multi_get(timeout=2.0)
 #   def alive_count (lst):
#async def parallel_request(obj_key, binary):
 #   r = http.request("PUT", "http://urllib.s3.us-east-2.amazonaws.com/" + obj_key, headers=headers, body=binary)#endpoint + "/results_up.txt")#, auth=auth)
  ## print(r.status)
"""
def get_response(request):
    return urllib3.request.urlopen(request).read()

@asyncio.coroutine
def read_page(loop, request):
    data = yield from loop.run_in_executor(None, lambda: get_response(request))
    print
#async def transfer_loop(num)
"""
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-G', '--GET', required=False, help='uses GET for the verb', action='store_true')
    parser.add_argument('-P', '--PUT', required=False, help='uses PUT for the verb', action='store_true')
    parser.add_argument('-t', '--numTransfers', required=False, help='number of transfers')
    parser.add_argument('-f', '--file_size', required=False, help='file size')
    args = parser.parse_args()
    """
    host_name = "http://urllib.s3.us-east-2.amazonaws.com"
    http = urllib3.PoolManager()
    print(http.headers)
    #for put request
    """
    
    headers = {"content-type":"text/plain"}#, "host":host_name, "content-length": obj_size}
    host_name = "http://urllib.s3.us-east-2.amazonaws.com/"
    num_transfers = int(args.numTransfers)
    obj_nums = range(0, num_transfers)
    http = urllib3.PoolManager()
    for i in range(num_transfers):
        obj_key = "result" + str(i)
        if args.GET:
           r = http.request("PUT", "http://urllib.s3.us-east-2.amazonaws.com/" + obj_key, headers=headers)
           #request = http.request.Request(host_name + obj_key, headers=headers, method="GET")
        if args.PUT:
            obj_size = int(args.file_size)
            body_stream = io.BytesIO(b'a' * obj_size)
            binary = body_stream.read()
            print(sys.getsizeof(body_stream))
            r = http.request("PUT", "http://urllib.s3.us-east-2.amazonaws.com/" + obj_key, headers=headers, body=binary)#endpoint + "/results_up.txt")#, auth=auth)
            #request = http.request.Request(host_name + obj_key, headers=headers, method="PUT", data=binary)
        print(r.headers)
        print(r.status)
    
    """
    
    #response = requests.get("http://urllib.s3.us-east-2.amazonaws.com/results_up.txt")
   # print(response.status_code)
   """
