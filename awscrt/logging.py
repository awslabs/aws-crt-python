# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

"""Python logging integration for the AWS CRT."""

import logging
import threading
from enum import IntEnum

import _awscrt
from awscrt.io import LogLevel

__all__ = ['init_logging', 'set_log_level', 'logf', 'LogSubject', 'CRT_LOG_FORMAT']

_CRT_TO_PY_LEVEL = {
    0: logging.NOTSET,
    1: logging.CRITICAL,
    2: logging.ERROR,
    3: logging.WARNING,
    4: logging.INFO,
    5: logging.DEBUG,
    6: logging.DEBUG,
}

_PY_TO_CRT_LEVEL = {
    logging.NOTSET: LogLevel.NoLogs,
    logging.CRITICAL: LogLevel.Fatal,
    logging.ERROR: LogLevel.Error,
    logging.WARNING: LogLevel.Warn,
    logging.INFO: LogLevel.Info,
    logging.DEBUG: LogLevel.Trace,
}

# Default Format supported by native loggers.
CRT_LOG_FORMAT = '%(asctime)s [%(threadName)s] %(levelname)s %(name)s - %(message)s'


class LogSubject(IntEnum):
    """Log subject identifiers for CRT subsystems."""
    # aws-c-common (package ID 0)
    COMMON_GENERAL = 0x000
    COMMON_TASK_SCHEDULER = 0x001

    # aws-c-io (package ID 1)
    IO_GENERAL = 0x400
    IO_EVENT_LOOP = 0x401
    IO_SOCKET = 0x402
    IO_SOCKET_HANDLER = 0x403
    IO_TLS = 0x404
    IO_ALPN = 0x405
    IO_DNS = 0x406
    IO_PKI = 0x407
    IO_CHANNEL = 0x408
    IO_CHANNEL_BOOTSTRAP = 0x409
    IO_FILE_UTILS = 0x40A
    IO_SHARED_LIBRARY = 0x40B

    # aws-c-http (package ID 2)
    HTTP_GENERAL = 0x800
    HTTP_CONNECTION = 0x801
    HTTP_SERVER = 0x802
    HTTP_STREAM = 0x803
    HTTP_CONNECTION_MANAGER = 0x804
    HTTP_WEBSOCKET = 0x805
    HTTP_WEBSOCKET_SETUP = 0x806

    # aws-c-event-stream (package ID 4)
    EVENT_STREAM_GENERAL = 0x1000
    EVENT_STREAM_CHANNEL_HANDLER = 0x1001
    EVENT_STREAM_RPC_SERVER = 0x1002
    EVENT_STREAM_RPC_CLIENT = 0x1003

    # aws-c-mqtt (package ID 5)
    MQTT_GENERAL = 0x1400
    MQTT_CLIENT = 0x1401
    MQTT_TOPIC_TREE = 0x1402

    # aws-c-auth (package ID 6)
    AUTH_GENERAL = 0x1800
    AUTH_PROFILE = 0x1801
    AUTH_CREDENTIALS_PROVIDER = 0x1802
    AUTH_SIGNING = 0x1803

    # aws-c-cal (package ID 7)
    CAL_GENERAL = 0x1C00
    CAL_ECC = 0x1C01
    CAL_HASH = 0x1C02
    CAL_HMAC = 0x1C03
    CAL_DER = 0x1C04
    CAL_LIBCRYPTO_RESOLVE = 0x1C05
    CAL_RSA = 0x1C06
    CAL_ED25519 = 0x1C07

    # aws-c-s3 (package ID 14)
    S3_GENERAL = 0x3800
    S3_CLIENT = 0x3801

    # aws-c-sdkutils (package ID 15)
    SDKUTILS_GENERAL = 0x3C00
    SDKUTILS_PROFILE = 0x3C01
    SDKUTILS_ENDPOINTS_PARSING = 0x3C02
    SDKUTILS_ENDPOINTS_RESOLVE = 0x3C03
    SDKUTILS_ENDPOINTS_GENERAL = 0x3C04
    SDKUTILS_PARTITIONS_PARSING = 0x3C05
    SDKUTILS_ENDPOINTS_REGEX = 0x3C06


_PACKAGE_ID_TO_MODULE = {
    0: 'common',
    1: 'io',
    2: 'http',
    4: 'event-stream',
    5: 'mqtt',
    6: 'auth',
    7: 'cal',
    14: 's3',
    15: 'sdkutils',
}


def _python_logging_callback(crt_level, message, subject_id, subject_name, thread_name):
    """Called from C for each CRT log message."""
    module = _PACKAGE_ID_TO_MODULE.get(subject_id >> 10, 'unknown')
    logger = logging.getLogger('awscrt.{}.{}'.format(module, subject_name))
    py_level = _CRT_TO_PY_LEVEL.get(crt_level, logging.DEBUG)
    # `There is the possibility that “dummy thread objects” are created. These are
    # thread objects corresponding to “alien threads”, which are threads of control
    # started outside the threading module, such as directly from C code.`
    # https://docs.python.org/3/library/threading.html#thread-objects
    #
    # As per current conventions, dummy thread objects have thread names
    # starting with "Dummy". Eg. Dummy-1, Dummy-8
    if threading.current_thread().name.startsWith("Dummy") and thread_name is not None:
        threading.current_thread().name = thread_name
    logger.log(py_level, '%s', message)


def init_logging(level: int = logging.DEBUG):
    """Initialize CRT logging, routing output through Python's logging module.

    Log messages appear under the ``awscrt`` logger hierarchy, with each CRT
    subsystem as a child logger (e.g. ``awscrt.io.event-loop``,
    ``awscrt.s3.S3Client``).

    This is mutually exclusive with :func:`~awscrt.io.init_logging` -- use one
    or the other, not both. Can only be called once.

    Example usage::

        import logging
        from awscrt.logging import init_logging

        logging.basicConfig(level=logging.DEBUG)
        init_logging(logging.DEBUG)

    Args:
        level (int): Python logging level (e.g. ``logging.DEBUG``,
            ``logging.WARNING``).

    Raises:
        RuntimeError: If CRT logging has already been initialized.
    """
    root_logger = logging.getLogger('awscrt')

    try:
        crt_level = _PY_TO_CRT_LEVEL[level]
    except KeyError:
        raise ValueError(f"Invalid log level: {level}. Use logging.DEBUG, INFO, WARNING, ERROR, or CRITICAL")

    if root_logger.level == logging.NOTSET:
        root_logger.setLevel(_CRT_TO_PY_LEVEL.get(int(crt_level), logging.DEBUG))

    _awscrt.init_python_logging(int(crt_level), _python_logging_callback)


def set_log_level(level: int):
    """Change the CRT log level. :func:`init_logging` must have been called first.

    Set log level to logging.NOTSET to disable the logger. Cleaning up the logger
    is dangerous in a multi-threaded environment.

    Args:
        level (int): Python logging level (e.g. ``logging.DEBUG``,
            ``logging.WARNING``).
    """
    try:
        crt_level = _PY_TO_CRT_LEVEL[level]
    except KeyError:
        raise ValueError(f"Invalid log level: {level}. Use logging.DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    _awscrt.set_log_level(int(crt_level))


def log(level: int, subject: LogSubject, message: str):
    """Log a message through the CRT's configured logger.

    Args:
        level (int): Python logging level (e.g. logging.DEBUG, logging.INFO).
        subject (LogSubject): Log subject identifying the subsystem.
        message (str): The message to log.
    """
    try:
        crt_level = _PY_TO_CRT_LEVEL[level]
    except KeyError:
        raise ValueError(f"Invalid log level: {level}. Use logging.DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    _awscrt.logger_log(int(crt_level), int(subject), message)
