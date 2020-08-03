import requests import time import datetime import hashlib import sys, os, base64, hmac from requests_aws4auth import AWS4Auth

                                                                                   if __name__ == "__main__" :
#access_key_id = "ASIA5AJLHVM7XXTRWGGD"
#secret_access_key = "xJDA+F4d7eJ8+eZnW7SHH2G08HAyZ4Dwd3KabymF"
#session_token =                                                                                                       \
    "IQoJb3JpZ2luX2VjELz//////////wEaCXVzLWVhc3QtMSJHMEUCIQCzFDKXA5kTEmg0O5FWhT7wN57pfpkrGKR/h6UQ+eBPLAIgSvXbeB1Zv0BRN/dRa/vnmlfj2hZoF4UPvciYsbrddKwqpwIIhP//////////ARAAGgw4OTM5ODA3NDg2MDciDPzbJ6Le9Nzu91o4BSr7AUPa8X3SlXrXoaYjNYJjhpT1uvNzRgR2NJym68wUVLLxjVzDqNufj+UJcaKvdG+B7066lxsZ2OEkh4RbZOuw86v9oKUK5PL7Wp78u4IST2NxFuzM6rLbK0kBZkeMuiAZ1cpp+rmeFW+Km5h8muKH3KQh469xh8rpRDsmPqpggVxav8YZy/nT06Ua1KFZj5EI8DkynodAR3ycRJsxtEskvjyCL14jdMQGaLnPDrtHamqPhVbiG3L28psD7OZxDutRczXD0CU8Wq7ZDf5KIkaDxkWmWYm09gvDwtkLGaUo7fXpEMv2miHQHraeyx94hq15CuL3LMpkcO63A3M+MML/nfkFOp0B770UmRjs54DfCXbPZFyyYWLjuF6KAZbkT6wpTuGLOIaEi2dZakCrqOHGqnNBTkJQUBhBK1HMUHdMWRShfeExv8b7X9sK4WQYb2fSg31GDyH9qBaP00dLYpNnYQlCwOtX4Fhp6MkbLDwxNYnWS2a6Zw41/fikUgm63Pxyb2bVM5ph4xDOeupqtEBZg9F2FnchmBHT2bPqKlizx+iWGQ=="
                                                                                   access_key_id = os.environ.get('AWS_ACCESS_KEY_ID') secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY') session_token = os.environ.get('AWS_SESSION_TOKEN')
#print(access_key_id)
#print(secret_access_key)
#print(session_token)
#request type, host and header info
                                                                                                                                                                                                                                      host_name = "crt-canary-bucket-ramosth.s3.us-east-2.amazonaws.com" region = "us-east-2" service = "s3" method = "GET" request_parameters = ""
#bucket_name = "crt-canary-bucket-ramosth-"
                                                                                                                                                                                                                                  key = "crt-canary-obj-single-part-" obj_num = 9223372036854775806
#url = "https://s3.amazonaws.com/crt-canary-bucket-ramosth"
                                                                                                                                                                                                                                  endpoint = "http://crt-canary-bucket-ramosth.s3.us-east-2.amazonaws.com" numTransfers = 1

                                                                                                                                                                                                                                  start = time.time() for i in range(numTransfers) : obj_key = "/" + key + str(obj_num) obj_num -= 1

                                                                                                                                                                                                                                  auth = AWS4Auth(access_key_id, secret_access_key, region, service, session_token = session_token) print("start request") response = requests.get(endpoint + obj_key, auth = auth) print(response.status_code, "\n")
#print(response.text)
                                                                                                                                                                                                                                                                                                                                                                                                                                                    end = time.time() total = end - start print("Time to complete in seconds: ", total)