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

#: Recommended format string for CRT log output. Includes timestamp, CRT thread
#: name, level, logger name, and message. Use with a :class:`logging.Handler`::
#:
#:     import logging
#:     from awscrt.logging import init_logging, CRT_LOG_FORMAT
#:
#:     handler = logging.StreamHandler()
#:     handler.setFormatter(logging.Formatter(CRT_LOG_FORMAT))
#:     logging.getLogger('awscrt').addHandler(handler)
#:     init_logging(logging.DEBUG)
CRT_LOG_FORMAT = '%(asctime)s [%(threadName)s] %(levelname)s %(name)s - %(message)s'


class LogSubject(IntEnum):
    """Log subject identifiers for CRT subsystems."""
    # aws-c-common
    CommonGeneral = 0x000
    CommonTaskScheduler = 0x001

    # aws-c-io
    IoGeneral = 0x400
    IoEventLoop = 0x401
    IoSocket = 0x402
    IoSocketHandler = 0x403
    IoTls = 0x404
    IoAlpn = 0x405
    IoDns = 0x406
    IoPki = 0x407
    IoChannel = 0x408
    IoChannelBootstrap = 0x409
    IoFileUtils = 0x40A
    IoSharedLibrary = 0x40B

    # aws-c-http
    HttpGeneral = 0x800
    HttpConnection = 0x801
    HttpServer = 0x802
    HttpStream = 0x803
    HttpConnectionManager = 0x804
    HttpWebsocket = 0x805
    HttpWebsocketSetup = 0x806

    # aws-c-mqtt
    MqttGeneral = 0x1400
    MqttClient = 0x1401
    MqttTopicTree = 0x1402

    # aws-c-auth
    AuthGeneral = 0x1800
    AuthProfile = 0x1801
    AuthCredentialsProvider = 0x1802
    AuthSigning = 0x1803

    # aws-c-s3
    S3General = 0x4000
    S3Client = 0x4001


def _python_logging_callback(crt_level, subject_name, message, thread_name, timestamp):
    """Called from C writer thread for each CRT log message."""
    logger = logging.getLogger('awscrt.{}'.format(subject_name))
    py_level = _CRT_TO_PY_LEVEL.get(crt_level, logging.DEBUG)
    record = logger.makeRecord(
        logger.name, py_level, '', 0, '%s', (message,), None
    )
    record.created = timestamp
    record.threadName = thread_name
    record.msecs = (timestamp - int(timestamp)) * 1000
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
