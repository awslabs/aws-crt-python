"""
I/O library for `awscrt`.

All networking in `awscrt` is asynchronous.
Long-running event-loop threads are used for concurrency.
"""

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

from __future__ import absolute_import
import _awscrt
from awscrt import NativeResource, isinstance_str
from enum import IntEnum
import io
import threading


class LogLevel(IntEnum):
    NoLogs = 0  #:
    Fatal = 1  #:
    Error = 2  #:
    Warn = 3  #:
    Info = 4  #:
    Debug = 5  #:
    Trace = 6  #:


def init_logging(log_level, file_name):
    """Initialize logging in `awscrt`.

    Args:
        log_level (LogLevel): Display messages of this importance and higher.
            `LogLevel.NoLogs` will disable logging.
        file_name (str): Logging destination. To write to stdout or stderr pass
            'stdout' or 'stderr' as strings. Otherwise, a file path is assumed.
    """
    assert log_level is not None
    assert file_name is not None

    _awscrt.init_logging(log_level, file_name)


class EventLoopGroup(NativeResource):
    """A collection of event-loops.

    An event-loop is a thread for doing async work, such as I/O. Classes that
    need to do async work will ask the EventLoopGroup for an event-loop to use.

    Args:
        num_threads (int): Number of event-loops to create.
            Pass 0 to create one for each processor on the machine.

    Attributes:
        shutdown_event (threading.Event): Signals when EventLoopGroup's threads
            have all finished shutting down. Shutdown begins when the
            EventLoopGroup object is destroyed.
    """

    __slots__ = ('shutdown_event')

    def __init__(self, num_threads=0):
        super(EventLoopGroup, self).__init__()

        shutdown_event = threading.Event()

        def on_shutdown():
            shutdown_event.set()

        self.shutdown_event = shutdown_event
        self._binding = _awscrt.event_loop_group_new(num_threads, on_shutdown)


class HostResolverBase(NativeResource):
    """DNS host resolver."""
    __slots__ = ()


class DefaultHostResolver(HostResolverBase):
    """Default DNS host resolver.

    Args:
        event_loop_group (EventLoopGroup): EventLoopGroup to use.
        max_hosts(int): Max host names to cache.
    """
    __slots__ = ()

    def __init__(self, event_loop_group, max_hosts=16):
        assert isinstance(event_loop_group, EventLoopGroup)

        super(DefaultHostResolver, self).__init__()
        self._binding = _awscrt.host_resolver_new_default(max_hosts, event_loop_group)


class ClientBootstrap(NativeResource):
    """Handles creation and setup of client socket connections.

    Args:
        event_loop_group (EventLoopGroup): EventLoopGroup to use.
        host_resolver (HostResolverBase): DNS host resolver to use.

    Attributes:
        shutdown_event (threading.Event): Signals when the ClientBootstrap's
            internal resources finish shutting down.
            Shutdown begins when the ClientBootstrap object is destroyed.
    """
    __slots__ = ('shutdown_event')

    def __init__(self, event_loop_group, host_resolver):
        assert isinstance(event_loop_group, EventLoopGroup)
        assert isinstance(host_resolver, HostResolverBase)

        super(ClientBootstrap, self).__init__()

        shutdown_event = threading.Event()

        def on_shutdown():
            shutdown_event.set()

        self.shutdown_event = shutdown_event
        self._binding = _awscrt.client_bootstrap_new(event_loop_group, host_resolver, on_shutdown)


def _read_binary_file(filepath):
    with open(filepath, mode='rb') as fh:
        contents = fh.read()
    return contents


class SocketDomain(IntEnum):
    IPv4 = 0  #:
    IPv6 = 1  #:
    Local = 2  #: Unix domain sockets (at at least something like them)


class SocketType(IntEnum):
    Stream = 0
    """A streaming socket sends reliable messages over a two-way connection.
    This means TCP when used with `SocketDomain.IPv4/6`,
    and Unix domain sockets when used with `SocketDomain.Local`"""

    DGram = 1
    """A datagram socket is connectionless and sends unreliable messages.
    This means UDP when used with `SocketDomain.IPv4/6`.
    `SocketDomain.Local` is not compatible with `DGram` """


class SocketOptions(object):
    """Socket options.

    Attributes:
        domain (SocketDomain): Socket domain.
        type (SocketType): Socket type.
        connect_timeout_ms (int): Connection timeout, in milliseconds.
        keep_alive (bool): If set True, periodically transmit keepalive messages
            for detecting a disconnected peer.
        keep_alive_timeout_secs (int): Duration, in seconds, between keepalive
            transmissions in idle condition. If 0, then a default value is used.
        keep_alive_interval_secs (int): Duration, in seconds, between keepalive
            retransmissions, if acknowledgement of previous keepalive transmission
            is not received. If 0, then a default value is used.
        keep_alive_max_probes (int): If set, sets the number of keepalive probes
            allowed to fail before a connection is considered lost.
    """

    __slots__ = (
        'domain', 'type', 'connect_timeout_ms', 'keep_alive',
        'keep_alive_timeout_secs', 'keep_alive_interval_secs', 'keep_alive_max_probes'
    )

    def __init__(self):
        for slot in self.__slots__:
            setattr(self, slot, None)

        self.domain = SocketDomain.IPv6
        self.type = SocketType.Stream
        self.connect_timeout_ms = 5000
        self.keep_alive = False
        self.keep_alive_interval_secs = 0
        self.keep_alive_timeout_secs = 0
        self.keep_alive_max_probes = 0


class TlsVersion(IntEnum):
    SSLv3 = 0  #:
    TLSv1 = 1  #:
    TLSv1_1 = 2  #:
    TLSv1_2 = 3  #:
    TLSv1_3 = 4  #:
    DEFAULT = 128  #:


class TlsContextOptions(object):
    """Options to create a TLS context.

    The static `TlsContextOptions.create_X()` methods provide common TLS configurations.
    A default-initialized TlsContextOptions has `verify_peer` set True.

    Attributes:
        min_tls_ver (TlsVersion): Minimum TLS version to use.
            System defaults are used by default.
        verify_peer (bool): Whether to validate the peer's x.509 certificate.
        alpn_list (Optional[List[str]]): If set, names to use in Application Layer
            Protocol Negotiation (ALPN). ALPN is not supported on all systems,
            see :meth:`is_alpn_available()`. This can be customized per connection,
            via :meth:`TlsConnectionOptions.set_alpn_list()`.
    """
    __slots__ = (
        'min_tls_ver', 'ca_dirpath', 'ca_buffer', 'alpn_list',
        'certificate_buffer', 'private_key_buffer',
        'pkcs12_filepath', 'pkcs12_password', 'verify_peer')

    def __init__(self):

        for slot in self.__slots__:
            setattr(self, slot, None)

        self.min_tls_ver = TlsVersion.DEFAULT
        self.verify_peer = True

    @staticmethod
    def create_client_with_mtls_from_path(cert_filepath, pk_filepath):
        """
        Create options configured for use with mutual TLS in client mode.

        Both files are treated as PKCS #7 PEM armored.
        They are loaded from disk and stored in buffers internally.

        Args:
            cert_filepath (str): Path to certificate file.
            pk_filepath (str): Path to private key file.

        Returns:
            TlsContextOptions:
        """

        assert isinstance_str(cert_filepath)
        assert isinstance_str(pk_filepath)

        cert_buffer = _read_binary_file(cert_filepath)
        key_buffer = _read_binary_file(pk_filepath)

        return TlsContextOptions.create_client_with_mtls(cert_buffer, key_buffer)

    @staticmethod
    def create_client_with_mtls(cert_buffer, key_buffer):
        """
        Create options configured for use with mutual TLS in client mode.

        Both buffers are treated as PKCS #7 PEM armored.

        Args:
            cert_buffer (bytes): Certificate contents
            key_buffer (bytes): Private key contents.

        Returns:
            TlsContextOptions:
        """
        assert isinstance(cert_buffer, bytes)
        assert isinstance(key_buffer, bytes)

        opt = TlsContextOptions()
        opt.certificate_buffer = cert_buffer
        opt.private_key_buffer = key_buffer

        opt.verify_peer = True
        return opt

    @staticmethod
    def create_client_with_mtls_pkcs12(pkcs12_filepath, pkcs12_password):
        """
        Create options configured for use with mutual TLS in client mode.

        NOTE: This configuration only works on Apple devices.

        Args:
            pkcs12_filepath (str): Path to PKCS #12 file.
                The file is loaded from disk and stored internally.
            pkcs12_password (str): Password to PKCS #12 file.

        Returns:
            TlsContextOptions:
        """

        assert isinstance_str(pkcs12_filepath)
        assert isinstance_str(pkcs12_password)

        opt = TlsContextOptions()
        opt.pkcs12_filepath = pkcs12_filepath
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = True
        return opt

    @staticmethod
    def create_server_from_path(cert_filepath, pk_filepath):
        """
        Create options configured for use in server mode.

        Both files are treated as PKCS #7 PEM armored.
        They are loaded from disk and stored in buffers internally.

        Args:
            cert_filepath (str): Path to certificate file.
            pk_filepath (str): Path to private key file.

        Returns:
            TlsContextOptions:
        """

        assert isinstance_str(cert_filepath)
        assert isinstance_str(pk_filepath)

        cert_buffer = _read_binary_file(cert_filepath)
        key_buffer = _read_binary_file(pk_filepath)

        return TlsContextOptions.create_server(cert_buffer, key_buffer)

    @staticmethod
    def create_server(cert_buffer, key_buffer):
        """
        Create options configured for use in server mode.

        Both buffers are treated as PKCS #7 PEM armored.

        Args:
            cert_buffer (bytes): Certificate contents.
            key_buffer (bytes): Private key contents.

        Returns:
            TlsContextOptions:
        """
        assert isinstance(cert_buffer, bytes)
        assert isinstance(key_buffer, bytes)

        opt = TlsContextOptions()
        opt.certificate_buffer = cert_buffer
        opt.private_key_buffer = key_buffer
        opt.verify_peer = False
        return opt

    @staticmethod
    def create_server_pkcs12(pkcs12_filepath, pkcs12_password):
        """
        Create options configured for use in server mode.

        NOTE: This configuration only works on Apple devices.

        Args:
            pkcs12_filepath (str): Path to PKCS #12 file.
            pkcs12_password (str): Password to PKCS #12 file.

        Returns:
            TlsContextOptions:
        """

        assert isinstance_str(pkcs12_filepath)
        assert isinstance_str(pkcs12_password)

        opt = TlsContextOptions()
        opt.pkcs12_filepath = pkcs12_filepath
        opt.pkcs12_password = pkcs12_password
        opt.verify_peer = False
        return opt

    def override_default_trust_store_from_path(self, ca_dirpath=None, ca_filepath=None):
        """Override default trust store.

        Args:
            ca_dirpath (Optional[str]): Path to directory containing
                trusted certificates, which will overrides the default trust store.
                Only supported on Unix.
            ca_filepath(Optional[str]): Path to file containing PEM armored chain
                of trusted CA certificates.
        """

        assert isinstance_str(ca_dirpath) or ca_dirpath is None
        assert isinstance_str(ca_filepath) or ca_filepath is None

        if ca_filepath:
            ca_buffer = _read_binary_file(ca_filepath)
            self.override_default_trust_store(ca_buffer)

        self.ca_dirpath = ca_dirpath

    def override_default_trust_store(self, rootca_buffer):
        """Override default trust store.

        Args:
            rootca_buffer (bytes): PEM armored chain of trusted CA certificates.
        """
        assert isinstance(rootca_buffer, bytes)

        self.ca_buffer = rootca_buffer


class ClientTlsContext(NativeResource):
    """Client TLS context.

    A context is expensive, but can be used for the lifetime of the application
    by all outgoing connections that wish to use the same TLS configuration.

    Args:
        options (TlsContextOptions): Configuration options.
    """
    __slots__ = ()

    def __init__(self, options):
        assert isinstance(options, TlsContextOptions)

        super(ClientTlsContext, self).__init__()
        self._binding = _awscrt.client_tls_ctx_new(
            options.min_tls_ver.value,
            options.ca_dirpath,
            options.ca_buffer,
            _alpn_list_to_str(options.alpn_list),
            options.certificate_buffer,
            options.private_key_buffer,
            options.pkcs12_filepath,
            options.pkcs12_password,
            options.verify_peer
        )

    def new_connection_options(self):
        """Create a :class:`TlsConnectionOptions` that makes use of this TLS context.

        Returns:
                TlsConnectionOptions:
        """
        return TlsConnectionOptions(self)


class TlsConnectionOptions(NativeResource):
    """Connection-specific TLS options.

    Note that, while a TLS context is an expensive object, a :class:`TlsConnectionOptions` is cheap.

    Args:
        tls_ctx (ClientTlsContext): TLS context. A context can be shared by many connections.

    Attributes:
        tls_ctx (ClientTlsContext): TLS context.
    """
    __slots__ = ('tls_ctx')

    def __init__(self, tls_ctx):
        assert isinstance(tls_ctx, ClientTlsContext)

        super(TlsConnectionOptions, self).__init__()
        self.tls_ctx = tls_ctx
        self._binding = _awscrt.tls_connections_options_new_from_ctx(tls_ctx)

    def set_alpn_list(self, alpn_list):
        """Set names to use in Application Layer Protocol Negotiation (ALPN).

        This overrides any ALPN list on the TLS context, see :attr:`TlsContextOptions.alpn_list`.
        ALPN is not supported on all systems, see :meth:`is_alpn_available()`.

        Args:
            alpn_list (List[str]): List of protocol names.
        """
        _awscrt.tls_connection_options_set_alpn_list(self, _alpn_list_to_str(alpn_list))

    def set_server_name(self, server_name):
        """Set server name.

        Sets name for TLS Server Name Indication (SNI).
        Name is also used for x.509 validation.

        Args:
            server_name (str): Server name.
        """
        _awscrt.tls_connection_options_set_server_name(self, server_name)


def _alpn_list_to_str(alpn_list):
    """
    Transform ['h2', 'http/1.1'] -> "h2;http/1.1"
    None is returned if list is None or empty
    """
    if alpn_list:
        assert not isinstance_str(alpn_list)
        return ';'.join(alpn_list)
    return None


def is_alpn_available():
    """Returns True if Application Layer Protocol Negotiation (ALPN)
    is supported on this system."""
    return _awscrt.is_alpn_available()


class InputStream(NativeResource):
    """InputStream allows `awscrt` native code to read from Python I/O classes.

    Args:
        stream (io.IOBase): Python I/O stream to wrap.
    """
    __slots__ = ()
    # TODO: Implement IOBase interface so Python can read from this class as well.

    def __init__(self, stream):
        assert isinstance(stream, io.IOBase)
        assert not isinstance(stream, InputStream)

        super(InputStream, self).__init__()
        self._binding = _awscrt.input_stream_new(stream)

    @classmethod
    def wrap(cls, stream, allow_none=False):
        """
        Given some stream type, returns an :class:`InputStream`.

        Args:
            stream (Union[io.IOBase, InputStream, None]): I/O stream to wrap.
            allow_none (bool): Whether to allow `stream` to be None.
                If False (default), and `stream` is None, an exception is raised.

        Returns:
            Union[InputStream, None]: If `stream` is already an :class:`InputStream`, it is returned.
            Otherwise, an :class:`InputStream` which wraps the `stream` is returned.
            If `allow_none` is True, and `stream` is None, then None is returned.
        """
        if isinstance(stream, InputStream):
            return stream
        if isinstance(stream, io.IOBase):
            return cls(stream)
        if stream is None and allow_none:
            return None
        raise TypeError('I/O stream type expected')
