import boto3
import time

if __name__ == "__main__":
    start = time.time()
    s3 = boto3.client('s3')
    print("download begin")
    s3.download_file("crt-canary-bucket-ramosth", "crt-canary-obj-single-part-9223372036854775806", "blank")
    end = time.time()
    print("success")
    print("Time to complete in seconds: ", (end - start))