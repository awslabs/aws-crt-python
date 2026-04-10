# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

"""Python logging integration for the AWS CRT."""

import logging
from enum import IntEnum

import _awscrt
from awscrt.io import LogLevel


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
    # aws-c-common
    COMMON_GENERAL = 0x000
    COMMON_TASK_SCHEDULER = 0x001

    # aws-c-io
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

    # aws-c-http
    HTTP_GENERAL = 0x800
    HTTP_CONNECTION = 0x801
    HTTP_SERVER = 0x802
    HTTP_STREAM = 0x803
    HTTP_CONNECTION_MANAGER = 0x804
    HTTP_WEBSOCKET = 0x805
    HTTP_WEBSOCKET_SETUP = 0x806

    # aws-c-mqtt
    MQTT_GENERAL = 0x1400
    MQTT_CLIENT = 0x1401
    MQTT_TOPIC_TREE = 0x1402

    # aws-c-auth
    AUTH_GENERAL = 0x1800
    AUTH_PROFILE = 0x1801
    AUTH_CREDENTIALS_PROVIDER = 0x1802
    AUTH_SIGNING = 0x1803

    # aws-c-s3
    S3_GENERAL = 0x3800
    S3_CLIENT = 0x3801


_PACKAGE_ID_TO_MODULE = {
    0: 'common',
    1: 'io',
    2: 'http',
    5: 'mqtt',
    6: 'auth',
    14: 's3',
}


def _python_logging_callback(crt_level, message, subject_id, subject_name, thread_name):
    """Called from C for each CRT log message."""
    module = _PACKAGE_ID_TO_MODULE.get(subject_id >> 10, 'unknown')
    logger = logging.getLogger('awscrt.{}.{}'.format(module, subject_name))
    py_level = _CRT_TO_PY_LEVEL.get(crt_level, logging.DEBUG)
    record = logger.makeRecord(
        logger.name, py_level, '', 0, '%s', (message,), None
    )
    record.threadName = thread_name
    logger.handle(record)


def init_logging(level: int):
    """Initialize CRT logging, routing output through Python's logging module.

    Log messages appear under the ``awscrt`` logger hierarchy, with each CRT
    subsystem as a child logger (e.g. ``awscrt.event-loop``,
    ``awscrt.task-scheduler``).

    A default handler with timestamp and thread name formatting is attached
    to the ``awscrt`` logger if it has no handlers yet.

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
    """
    root_logger = logging.getLogger('awscrt')

    crt_level = _PY_TO_CRT_LEVEL.get(level, LogLevel.Warn)

    if root_logger.level == logging.NOTSET:
        root_logger.setLevel(_CRT_TO_PY_LEVEL.get(int(crt_level), logging.DEBUG))

    _awscrt.init_python_logging(int(crt_level), _python_logging_callback)


def set_log_level(level: int):
    """Change the CRT log level. :func:`init_logging` must have been called first.

    Args:
        level (int): Python logging level (e.g. ``logging.DEBUG``,
            ``logging.WARNING``).
    """
    crt_level = _PY_TO_CRT_LEVEL.get(level, LogLevel.Warn)
    _awscrt.set_log_level(int(crt_level))


def logf(level: int, subject: LogSubject, message: str):
    """Log a message through the CRT's configured logger.

    Args:
        level (int): Python logging level (e.g. logging.DEBUG, logging.INFO).
        subject (LogSubject): Log subject identifying the subsystem.
        message (str): The message to log.
    """
    crt_level = _PY_TO_CRT_LEVEL.get(level, LogLevel.Warn)
    _awscrt.logger_log(int(crt_level), int(subject), message)
