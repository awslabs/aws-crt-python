import argparse
import subprocess
import sys
import time

DEFAULT_TIMEOUT = 1800
DEFAULT_INTERVAL = 5
DEFAULT_INDEX_URL = 'https://pypi.org/simple'


def wait(package, version, index_url=DEFAULT_INDEX_URL, timeout=DEFAULT_TIMEOUT, interval=DEFAULT_INTERVAL):
    give_up_time = time.time() + timeout
    while True:
        output = subprocess.check_output([sys.executable, '-m', 'pip', '--index', index_url, 'search', package])
        output = output.decode()

        # output looks like: 'awscrt (0.3.1)  - A common runtime for AWS Python projects\n...'
        if output.startswith('{} ({})'.format(package, version)):
            return True

        if time.time() >= give_up_time:
            return False

        time.sleep(interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('package', help="Packet name")
    parser.add_argument('version', help="Package version")
    parser.add_argument('-i', '--index-url', default=DEFAULT_INDEX_URL, help="PyPI URL")
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT, help="Give up after N seconds.")
    parser.add_argument('--interval', type=float, default=DEFAULT_INTERVAL, help="Query PyPI every N seconds")
    args = parser.parse_args()

    if wait(args.package, args.version, args.index_url, args.timeout, args.interval):
        print('{} {} is available in pypi'.format(args.package, args.version))
    else:
        exit("Timed out waiting for pypi to report {} {} as latest".format(args.package, args.version))
