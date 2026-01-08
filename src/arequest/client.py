"""High-performance async HTTP client.

This module provides a high-performance HTTP client with:
- Connection pooling with keep-alive
- True concurrent request handling
- Optimized HTTP parsing (C extension when available)
- Zero-copy buffer management
- requests-like API

Example:
    import asyncio
    import arequest
    
    async def main():
        # Simple request
        response = await arequest.get('https://httpbin.org/get')
        print(response.json())
        
        # Using session for connection reuse
        async with arequest.Session() as session:
            resp = await session.get('https://httpbin.org/get')
            print(resp.status_code)
    
    asyncio.run(main())
"""

import asyncio
import os
import socket
import ssl
import time
import uuid
import zlib
from typing import TYPE_CHECKING, Any, Optional, Union
from urllib.parse import urlencode, urlparse

if TYPE_CHECKING:
    from .auth import AuthBase

# Use fast parser with httptools support
try:
    from .parser import FastHTTPParser, FastHTTPRequestBuilder
    _HAS_FAST_PARSER = True
except ImportError:
    _HAS_FAST_PARSER = False


def _decompress(body: bytes, encoding: str) -> bytes:
    """Decompress response body based on Content-Encoding."""
    if not body:
        return body
    encoding = encoding.lower()
    if encoding == 'gzip':
        return zlib.decompress(body, zlib.MAX_WBITS | 16)
    elif encoding == 'deflate':
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def _build_multipart_formdata(
    data: Optional[dict] = None,
    files: Optional[dict] = None,
) -> tuple[bytes, str]:
    """Build multipart/form-data body like requests library."""
    boundary = uuid.uuid4().hex
    parts = []
    
    if data:
        for name, value in data.items():
            if value is None:
                continue
            part = f'--{boundary}\r\n'
            part += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            part += f'{value}\r\n'
            parts.append(part.encode('utf-8'))
    
    if files:
        for field_name, file_info in files.items():
            if isinstance(file_info, tuple):
                if len(file_info) >= 2:
                    filename = file_info[0]
                    file_content = file_info[1]
                    content_type = file_info[2] if len(file_info) >= 3 else None
                    
                    if isinstance(file_content, bytes):
                        content = file_content
                    elif isinstance(file_content, str):
                        content = file_content.encode('utf-8')
                    elif hasattr(file_content, 'read'):
                        content = file_content.read()
                        if isinstance(content, str):
                            content = content.encode('utf-8')
                    else:
                        content = str(file_content).encode('utf-8')
                    
                    if filename is None:
                        part = f'--{boundary}\r\n'.encode('utf-8')
                        part += f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode('utf-8')
                        part += content
                        part += b'\r\n'
                    else:
                        if content_type is None:
                            ext = os.path.splitext(filename)[1].lower()
                            mime_types = {
                                '.txt': 'text/plain', '.html': 'text/html', '.css': 'text/css',
                                '.js': 'application/javascript', '.json': 'application/json',
                                '.xml': 'application/xml', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                                '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp',
                                '.pdf': 'application/pdf', '.zip': 'application/zip',
                            }
                            content_type = mime_types.get(ext, 'application/octet-stream')
                        part = f'--{boundary}\r\n'.encode('utf-8')
                        part += f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode('utf-8')
                        part += f'Content-Type: {content_type}\r\n\r\n'.encode('utf-8')
                        part += content
                        part += b'\r\n'
                    parts.append(part)
                else:
                    continue
            elif isinstance(file_info, bytes):
                part = f'--{boundary}\r\n'.encode('utf-8')
                part += f'Content-Disposition: form-data; name="{field_name}"; filename="{field_name}"\r\n'.encode('utf-8')
                part += b'Content-Type: application/octet-stream\r\n\r\n'
                part += file_info
                part += b'\r\n'
                parts.append(part)
            elif isinstance(file_info, str):
                if os.path.isfile(file_info):
                    with open(file_info, 'rb') as f:
                        content = f.read()
                    filename = os.path.basename(file_info)
                    part = f'--{boundary}\r\n'.encode('utf-8')
                    part += f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode('utf-8')
                    part += b'Content-Type: application/octet-stream\r\n\r\n'
                    part += content
                    part += b'\r\n'
                    parts.append(part)
                else:
                    part = f'--{boundary}\r\n'
                    part += f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'
                    part += f'{file_info}\r\n'
                    parts.append(part.encode('utf-8'))
            elif hasattr(file_info, 'read'):
                content = file_info.read()
                if isinstance(content, str):
                    content = content.encode('utf-8')
                filename = os.path.basename(getattr(file_info, 'name', field_name))
                part = f'--{boundary}\r\n'.encode('utf-8')
                part += f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode('utf-8')
                part += b'Content-Type: application/octet-stream\r\n\r\n'
                part += content
                part += b'\r\n'
                parts.append(part)
    
    parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
    
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


class Response:
    """HTTP response with lazy decoding, fully compatible with requests.Response API."""
    
    __slots__ = (
        'status_code', 'headers', 'url', '_body', '_text', '_json_data',
        'reason', 'request_info', 'elapsed', 'ok', 'encoding', 'history',
        'cookies', 'links', 'is_redirect', 'is_permanent_redirect'
    )
    
    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        body: bytes,
        url: str,
        reason: str = "",
        elapsed: float = 0.0,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self.url = url
        self._body = body
        self._text: Optional[str] = None
        self._json_data = None
        self.reason = reason
        self.elapsed = elapsed
        self.request_info = None
        self.ok = status_code < 400
        # Lazy encoding detection for better performance
        self.encoding: Optional[str] = None
        # Requests-compatible attributes
        self.history: list['Response'] = []
        self.cookies: dict[str, str] = {}
        self.links: dict = {}
        self.is_redirect = status_code in (301, 302, 303, 307, 308)
        self.is_permanent_redirect = status_code in (301, 308)
    
    @property
    def content(self) -> bytes:
        """Get raw response body."""
        return self._body
    
    @property
    def text(self) -> str:
        """Get response body as text (requests-like) with lazy decoding."""
        if self._text is None:
            if self.encoding is None:
                self.encoding = self._detect_encoding()
            self._text = self._body.decode(self.encoding, errors='replace')
        return self._text
    
    def decode(self, encoding: Optional[str] = None) -> str:
        """Decode response body with an optional encoding override."""
        if encoding is None:
            return self.text
        return self._body.decode(encoding, errors='replace')
    
    def json(self) -> Any:
        """Parse response body as JSON (requests-like) with optimized parsing."""
        if self._json_data is None:
            import json as json_module
            # Try orjson first (faster), but handle encoding errors gracefully
            try:
                import orjson
                try:
                    self._json_data = orjson.loads(self._body)
                except (orjson.JSONDecodeError, UnicodeDecodeError):
                    # Fallback to standard json with text (handles encoding issues)
                    try:
                        self._json_data = json_module.loads(self.text)
                    except json_module.JSONDecodeError as e:
                        # Provide helpful error message with response preview
                        preview = self.text[:200] if len(self.text) <= 200 else self.text[:200] + '...'
                        raise ValueError(
                            f"Response is not valid JSON. Status: {self.status_code}, "
                            f"Content-Type: {self.headers.get('Content-Type', 'unknown')}, "
                            f"Body preview: {repr(preview)}"
                        ) from e
            except ImportError:
                try:
                    self._json_data = json_module.loads(self.text)
                except json_module.JSONDecodeError as e:
                    # Provide helpful error message with response preview
                    preview = self.text[:200] if len(self.text) <= 200 else self.text[:200] + '...'
                    raise ValueError(
                        f"Response is not valid JSON. Status: {self.status_code}, "
                        f"Content-Type: {self.headers.get('Content-Type', 'unknown')}, "
                        f"Body preview: {repr(preview)}"
                    ) from e
        return self._json_data
    
    def _detect_encoding(self) -> str:
        """Detect encoding from Content-Type header."""
        ct = self.headers.get('Content-Type', '')
        if 'charset=' in ct:
            return ct.split('charset=')[-1].split(';')[0].strip()
        return 'utf-8'
    
    def raise_for_status(self) -> None:
        """Raise exception for 4xx/5xx status codes (requests-compatible)."""
        if 400 <= self.status_code < 500:
            raise ClientError(f"{self.status_code} Client Error: {self.reason} for url: {self.url}", self.status_code)
        elif self.status_code >= 500:
            raise ServerError(f"{self.status_code} Server Error: {self.reason} for url: {self.url}", self.status_code)
    
    def iter_content(self, chunk_size: int = 1024):
        """Iterate over response content in chunks (requests-compatible)."""
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]
    
    def iter_lines(self, delimiter: bytes = b'\n'):
        """Iterate over response lines (requests-compatible)."""
        lines = self._body.split(delimiter)
        for line in lines:
            if line:
                yield line
    
    @property
    def apparent_encoding(self) -> str:
        """The apparent encoding (requests-compatible)."""
        # Simplified version - in production would use chardet
        return self._detect_encoding()
    
    def __repr__(self) -> str:
        return f"<Response [{self.status_code}]>"
    
    async def __aenter__(self) -> "Response":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class ClientError(Exception):
    """Client error (4xx)."""
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class ServerError(Exception):
    """Server error (5xx)."""
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class TimeoutError(Exception):
    """Request timeout error."""
    pass


class _ConnectionPool:
    """Ultra high-performance connection pool for a single host."""
    
    __slots__ = (
        'host', 'port', 'ssl_context', 'max_size', 'max_idle_time',
        '_available', '_in_use', '_closed', '_dns_cache',
        '_dns_expire', '_creating', '_host_bytes'
    )
    
    def __init__(
        self,
        host: str,
        port: int,
        ssl_context: Optional[ssl.SSLContext] = None,
        max_size: int = 100,
        max_idle_time: float = 60.0,  # Increased for better reuse
    ):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.max_size = max_size
        self.max_idle_time = max_idle_time
        
        self._available: list[tuple[asyncio.StreamReader, asyncio.StreamWriter, float]] = []
        self._in_use: set[asyncio.StreamWriter] = set()
        self._closed = False
        self._dns_cache: Optional[list[tuple]] = None
        self._dns_expire: float = 0
        self._creating: int = 0
        self._host_bytes = host.encode('ascii')  # Pre-encode for speed
    
    async def _resolve_dns(self) -> list[tuple]:
        """Resolve and cache DNS with longer TTL."""
        now = time.monotonic()
        if self._dns_cache and self._dns_expire > now:
            return self._dns_cache
        
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(
            self.host, self.port,
            type=2,  # SOCK_STREAM
            proto=6,  # IPPROTO_TCP
        )
        self._dns_cache = infos
        self._dns_expire = now + 300.0  # 5 minute DNS cache
        return infos
    
    async def acquire(self, timeout: Optional[float] = None) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Get a connection from pool with optimized fast path."""
        if self._closed:
            raise RuntimeError("Pool is closed")
        
        now = time.monotonic()
        # Fast path: pop from end (most recently used, likely still valid)
        while self._available:
            reader, writer, created = self._available.pop()
            if not writer.is_closing() and (now - created) <= self.max_idle_time:
                self._in_use.add(writer)
                return reader, writer
            # Silently discard stale connection
            try:
                writer.close()
            except Exception:
                pass
        
        try:
            self._creating += 1
            if timeout:
                reader, writer = await asyncio.wait_for(
                    self._create_connection(),
                    timeout=timeout
                )
            else:
                reader, writer = await self._create_connection()
            self._in_use.add(writer)
            return reader, writer
        except asyncio.TimeoutError:
            raise TimeoutError(f"Connection timeout to {self.host}:{self.port}")
        finally:
            self._creating -= 1
    
    async def _create_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Create a new connection with optimized settings."""
        infos = await self._resolve_dns()
        
        last_exc = None
        for family, type_, proto, canonname, sockaddr in infos:
            try:
                reader, writer = await asyncio.open_connection(
                    sockaddr[0],
                    self.port,
                    ssl=self.ssl_context,
                    server_hostname=self.host if self.ssl_context else None,
                )
                
                # Optimize socket for low latency and high throughput
                sock = writer.get_extra_info('socket')
                if sock:
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 524288)  # 512KB
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 131072)  # 128KB
                    except (OSError, AttributeError):
                        pass
                
                return reader, writer
            except Exception as e:
                last_exc = e
                continue
        
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Could not connect to {self.host}:{self.port}")
    
    def release(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, keep_alive: bool = True) -> None:
        """Release connection back to pool with optimized management."""
        if writer in self._in_use:
            self._in_use.discard(writer)
        
        if self._closed or not keep_alive or writer.is_closing():
            if not writer.is_closing():
                writer.close()
            return
        
        # Optimize pool size management
        if len(self._available) < self.max_size:
            # Add to front of list for LRU-like behavior
            self._available.insert(0, (reader, writer, time.monotonic()))
        else:
            writer.close()
    
    async def close(self) -> None:
        """Close all connections."""
        self._closed = True
        
        for reader, writer, _ in self._available:
            if not writer.is_closing():
                writer.close()
        self._available.clear()
        
        for writer in list(self._in_use):
            if not writer.is_closing():
                writer.close()
        self._in_use.clear()


class _SimpleHTTPParser:
    """Minimal HTTP response parser with optimizations (fallback when httptools not available)."""
    
    __slots__ = ('status_code', 'reason', 'headers', 'body', 'keep_alive', '_content_length', '_chunked', 'set_cookies')
    
    def __init__(self):
        self.status_code = 0
        self.reason = ""
        self.headers = {}
        self.body = b""
        self.keep_alive = True
        self._content_length = None
        self._chunked = False
        self.set_cookies: list[str] = []  # Store all Set-Cookie headers
    
    async def parse(self, reader: asyncio.StreamReader) -> None:
        header_bytes = await reader.readuntil(b'\r\n\r\n')
        
        status_end = header_bytes.find(b'\r\n')
        status_line = header_bytes[:status_end]
        parts = status_line.split(b' ', 2)
        self.status_code = int(parts[1])
        self.reason = parts[2].decode('latin-1') if len(parts) > 2 else ""
        
        # Optimized header parsing with byte comparisons
        content_length_key = b'content-length'
        transfer_encoding_key = b'transfer-encoding'
        connection_key = b'connection'
        set_cookie_key = b'set-cookie'
        
        for line in header_bytes[status_end+2:-4].split(b'\r\n'):
            if not line:
                break
            colon = line.find(b':')
            if colon > 0:
                key = line[:colon].decode('latin-1')
                value = line[colon+1:].strip().decode('latin-1')
                
                kl_bytes = line[:colon].lower()
                if kl_bytes == set_cookie_key:
                    self.set_cookies.append(value)
                else:
                    self.headers[key] = value
                
                if kl_bytes == content_length_key:
                    self._content_length = int(value)
                elif kl_bytes == transfer_encoding_key:
                    if b'chunked' in line[colon+1:].lower():
                        self._chunked = True
                elif kl_bytes == connection_key:
                    if b'close' in line[colon+1:].lower():
                        self.keep_alive = False
        
        if self._chunked:
            await self._read_chunked(reader)
        elif self._content_length:
            self.body = await reader.readexactly(self._content_length)
    
    async def _read_chunked(self, reader: asyncio.StreamReader) -> None:
        chunks = []
        while True:
            size_line = await reader.readline()
            size = int(size_line.strip().split(b';')[0], 16)
            if size == 0:
                await reader.readline()
                break
            chunks.append(await reader.readexactly(size))
            await reader.readexactly(2)
        self.body = b''.join(chunks) if len(chunks) > 1 else (chunks[0] if chunks else b'')


class _SimpleHTTPBuilder:
    """Simple HTTP request builder with basic optimizations."""
    
    # Pre-encoded constants
    _HTTP11 = b' HTTP/1.1\r\n'
    _CRLF = b'\r\n'
    _COLON_SPACE = b': '
    
    @staticmethod
    def build(method: str, path: str, headers: dict[str, str], body: Optional[bytes] = None) -> bytes:
        parts = [
            method.encode('ascii'),
            b' ',
            path.encode('ascii') if isinstance(path, str) else path,
            _SimpleHTTPBuilder._HTTP11,
        ]
        for k, v in headers.items():
            parts.append(k.encode('ascii'))
            parts.append(_SimpleHTTPBuilder._COLON_SPACE)
            parts.append(v.encode('latin-1') if isinstance(v, str) else v)
            parts.append(_SimpleHTTPBuilder._CRLF)
        parts.append(_SimpleHTTPBuilder._CRLF)
        if body:
            parts.append(body)
        return b''.join(parts)


class Session:
    """Ultra high-performance HTTP session optimized for web scraping.
    
    Drop-in async replacement for requests.Session with aggressive optimizations:
    - Connection pooling with keep-alive
    - DNS caching (5 minute TTL)
    - Pre-cached SSL contexts
    - Automatic cookie handling
    - Zero-copy header building
    
    Example:
        # Async usage (recommended for performance)
        async with Session() as session:
            response = await session.get('https://example.com')
            print(response.text)
        
        # Or using session directly
        session = Session()
        response = await session.get('https://example.com')
        await session.close()
    """
    
    __slots__ = (
        '_pools', '_default_headers', '_default_timeout', '_ssl_contexts',
        '_closed', '_connector_limit', '_connector_limit_per_host',
        '_parser_class', '_builder_class', 'auth', 'cookies', 'verify',
        'proxies', 'hooks', 'params', 'stream', 'cert', 'max_redirects',
        'trust_env', '_host_header_cache', '_cookie_cache', '_cookie_cache_valid'
    )
    
    # Pre-create SSL contexts at class level for sharing across sessions
    _SHARED_SSL_VERIFIED: Optional[ssl.SSLContext] = None
    _SHARED_SSL_UNVERIFIED: Optional[ssl.SSLContext] = None
    
    def __init__(
        self,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        connector_limit: int = 100,
        connector_limit_per_host: int = 50,  # Increased for web scraping
        auth: "Optional[AuthBase]" = None,
        verify: bool = True,
    ):
        """Initialize session with optimized defaults for web scraping.
        
        Args:
            headers: Default headers for all requests
            timeout: Default timeout in seconds
            connector_limit: Total connection limit
            connector_limit_per_host: Per-host connection limit
            auth: Default authentication
            verify: SSL verification (default True)
        """
        self._pools: dict[tuple[str, int, bool], _ConnectionPool] = {}
        self._default_headers = headers.copy() if headers else {}
        self._default_timeout = timeout
        self._ssl_contexts: dict[bool, ssl.SSLContext] = {}
        self._closed = False
        self._connector_limit = connector_limit
        self._connector_limit_per_host = connector_limit_per_host
        self.auth = auth
        self.cookies: dict[str, str] = {}
        self.verify = verify
        
        # Caches for speed
        self._host_header_cache: dict[tuple[str, int], str] = {}
        self._cookie_cache: str = ""
        self._cookie_cache_valid: bool = False
        
        # Additional requests-compatible attributes
        self.proxies: dict[str, str] = {}
        self.hooks: dict = {}
        self.params: dict = {}
        self.stream: bool = False
        self.cert: Optional[str] = None
        self.max_redirects: int = 30
        self.trust_env: bool = True
        
        if _HAS_FAST_PARSER:
            self._parser_class = FastHTTPParser
            self._builder_class = FastHTTPRequestBuilder
        else:
            self._parser_class = _SimpleHTTPParser
            self._builder_class = _SimpleHTTPBuilder
    
    @property
    def headers(self) -> dict[str, str]:
        """Get default headers (requests-compatible property)."""
        return self._default_headers
    
    @headers.setter
    def headers(self, value: dict[str, str]) -> None:
        """Set default headers (requests-compatible property)."""
        self._default_headers = value.copy() if value else {}
    
    @classmethod
    def _get_shared_ssl_context(cls, verify: bool = True) -> ssl.SSLContext:
        """Get shared SSL context (created once, shared across all sessions)."""
        if verify:
            if cls._SHARED_SSL_VERIFIED is None:
                ctx = ssl.create_default_context()
                # Optimize SSL settings
                ctx.check_hostname = True
                ctx.verify_mode = ssl.CERT_REQUIRED
                cls._SHARED_SSL_VERIFIED = ctx
            return cls._SHARED_SSL_VERIFIED
        else:
            if cls._SHARED_SSL_UNVERIFIED is None:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                cls._SHARED_SSL_UNVERIFIED = ctx
            return cls._SHARED_SSL_UNVERIFIED
    
    def _get_ssl_context(self, verify: bool = True) -> ssl.SSLContext:
        """Get SSL context (uses shared context for speed)."""
        return self._get_shared_ssl_context(verify)
    
    def _extract_cookies(self, set_cookies: list[str]) -> None:
        """Extract and store cookies from Set-Cookie headers."""
        if not set_cookies:
            return
        for cookie_str in set_cookies:
            # Parse cookie - extract name=value before any ;
            idx = cookie_str.find(';')
            parts = cookie_str[:idx] if idx > 0 else cookie_str
            eq_idx = parts.find('=')
            if eq_idx > 0:
                name = parts[:eq_idx].strip()
                val = parts[eq_idx+1:].strip()
                self.cookies[name] = val
        self._cookie_cache_valid = False  # Invalidate cookie cache
    
    def _get_cookie_header(self) -> str:
        """Get cached cookie header string."""
        if not self._cookie_cache_valid and self.cookies:
            self._cookie_cache = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
            self._cookie_cache_valid = True
        return self._cookie_cache
    
    def _get_host_header(self, host: str, port: int) -> str:
        """Get cached Host header value."""
        key = (host, port)
        if key not in self._host_header_cache:
            self._host_header_cache[key] = host if port in (80, 443) else f"{host}:{port}"
        return self._host_header_cache[key]
    
    def _get_pool(self, host: str, port: int, is_ssl: bool, verify: bool = True) -> _ConnectionPool:
        """Get or create connection pool for host."""
        """Get or create connection pool for host."""
        key = (host, port, is_ssl)
        if key not in self._pools:
            ssl_ctx = self._get_ssl_context(verify) if is_ssl else None
            self._pools[key] = _ConnectionPool(
                host=host,
                port=port,
                ssl_context=ssl_ctx,
                max_size=self._connector_limit_per_host,
            )
        return self._pools[key]
    
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        data: Optional[Union[bytes, str, dict]] = None,
        json: Optional[Any] = None,
        files: Optional[dict] = None,
        timeout: Optional[float] = None,
        verify: Optional[bool] = None,
        allow_redirects: bool = True,
        max_redirects: int = 10,
        auth: "Optional[AuthBase]" = None,
    ) -> Response:
        """Make an HTTP request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            headers: Request headers
            params: Query parameters
            data: Form data or raw body
            json: JSON body (auto-serialized)
            files: Files for multipart upload. Values can be:
                   - tuple: (filename, content, content_type)
                   - bytes: raw file content
                   - str: file path
                   - file-like object
            timeout: Request timeout
            verify: SSL verification
            allow_redirects: Follow redirects
            max_redirects: Max redirect count
            auth: Authentication
            
        Returns:
            Response object
        """
        if self._closed:
            raise RuntimeError("Session is closed")
        
        start_time = time.perf_counter()
        
        # Fast URL parsing
        parsed = urlparse(url)
        scheme = parsed.scheme
        host = parsed.hostname or ''
        port = parsed.port or (443 if scheme == 'https' else 80)
        path = parsed.path or '/'
        if parsed.query:
            path = f"{path}?{parsed.query}"
        
        if params:
            sep = '&' if '?' in path else '?'
            path = f"{path}{sep}{urlencode(params)}"
        
        is_ssl = scheme == 'https'
        verify_ssl = verify if verify is not None else self.verify
        
        # Optimize header merging with case-insensitive handling
        if headers:
            req_headers = {**self._default_headers, **headers}
        else:
            req_headers = self._default_headers.copy() if self._default_headers else {}
        
        # Normalize common header keys to proper case (HTTP headers are case-insensitive)
        header_lower_map = {k.lower(): k for k in req_headers}
        
        # Helper to check if header exists (case-insensitive)
        def has_header(name: str) -> bool:
            return name.lower() in header_lower_map
        
        # Helper to get/set header (normalizes to proper case)
        def set_header(name: str, value: str, force: bool = False) -> None:
            lower_name = name.lower()
            if lower_name in header_lower_map and not force:
                return
            if lower_name in header_lower_map:
                del req_headers[header_lower_map[lower_name]]
            req_headers[name] = value
            header_lower_map[lower_name] = name
        
        # Set required headers
        set_header('Host', self._get_host_header(host, port))
        set_header('Connection', 'keep-alive')
        set_header('Accept-Encoding', 'gzip, deflate')
        set_header('User-Agent', 'Mozilla/5.0 (compatible; arequest/1.1.0)')
        
        # Add cookies to request
        if self.cookies and not has_header('Cookie'):
            cookie_str = self._get_cookie_header()
            if cookie_str:
                set_header('Cookie', cookie_str)
        
        # Apply authentication
        request_auth = auth or self.auth
        if request_auth and hasattr(request_auth, 'apply'):
            class _TempReq:
                headers = req_headers
            request_auth.apply(_TempReq())
        
        # Build request body with automatic Content-Type and Accept headers
        body: Optional[bytes] = None
        
        # Priority: files > json > data (same as requests)
        if files is not None:
            body, content_type = _build_multipart_formdata(data if isinstance(data, dict) else None, files)
            # MUST force Content-Type because boundary in body must match header
            set_header('Content-Type', content_type, force=True)
            set_header('Accept', '*/*')
        elif json is not None:
            try:
                import orjson
                body = orjson.dumps(json)
            except ImportError:
                import json as json_module
                body = json_module.dumps(json, separators=(',', ':')).encode('utf-8')
            # For JSON requests, FORCE proper headers (GraphQL APIs require this)
            set_header('Content-Type', 'application/json', force=True)
            set_header('Accept', 'application/json', force=True)
        elif data is not None:
            if isinstance(data, dict):
                body = urlencode(data).encode('utf-8')
                set_header('Content-Type', 'application/x-www-form-urlencoded')
            elif isinstance(data, str):
                body = data.encode('utf-8')
                set_header('Content-Type', 'text/plain; charset=utf-8')
            else:
                body = data
            set_header('Accept', '*/*')
        else:
            set_header('Accept', '*/*')
        
        if body:
            set_header('Content-Length', str(len(body)), force=True)
            if method.upper() in ('POST', 'PUT', 'PATCH'):
                set_header('Origin', f"{scheme}://{host}" if port in (80, 443) else f"{scheme}://{host}:{port}")
        
        request_bytes = self._builder_class.build(method.upper(), path, req_headers, body)
        
        pool = self._get_pool(host, port, is_ssl, verify_ssl)
        timeout_val = timeout or self._default_timeout
        
        reader = writer = None
        try:
            reader, writer = await pool.acquire(timeout=timeout_val)
            
            writer.write(request_bytes)
            await writer.drain()
            
            parser = self._parser_class()
            await parser.parse(reader)
            
            elapsed = time.perf_counter() - start_time
            
            # Decompress response body if needed
            body = parser.body
            content_encoding = parser.headers.get('Content-Encoding', '')
            
            # Try decompression if Content-Encoding header is present
            if content_encoding:
                try:
                    body = _decompress(body, content_encoding)
                except Exception:
                    pass  # Use original body if decompression fails
            
            # Auto-detect gzip even without Content-Encoding header (some servers misconfigure this)
            elif body and len(body) >= 2 and body[:2] == b'\x1f\x8b':
                try:
                    body = _decompress(body, 'gzip')
                except Exception:
                    pass  # Use original body if decompression fails
            
            response = Response(
                status_code=parser.status_code,
                headers=parser.headers,
                body=body,
                url=url,
                reason=parser.reason,
                elapsed=elapsed,
            )
            
            # Store cookies from Set-Cookie headers
            self._extract_cookies(parser.set_cookies)
            
            pool.release(reader, writer, keep_alive=parser.keep_alive)
            reader = writer = None
            
            if allow_redirects and response.status_code in (301, 302, 303, 307, 308):
                if max_redirects > 0:
                    location = response.headers.get('Location', '')
                    if location:
                        if not location.startswith('http'):
                            location = f"{scheme}://{host}:{port}{location}"
                        return await self.request(
                            'GET' if response.status_code == 303 else method,
                            location,
                            headers=headers,
                            timeout=timeout,
                            verify=verify,
                            allow_redirects=True,
                            max_redirects=max_redirects - 1,
                        )
            
            return response
            
        except asyncio.TimeoutError:
            if reader and writer:
                pool.release(reader, writer, keep_alive=False)
            raise TimeoutError(f"Request timeout: {url}")
        except Exception:
            if reader and writer:
                pool.release(reader, writer, keep_alive=False)
            raise
    
    async def get(self, url: str, **kwargs) -> Response:
        """Make GET request."""
        return await self.request('GET', url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> Response:
        """Make POST request."""
        return await self.request('POST', url, **kwargs)
    
    async def put(self, url: str, **kwargs) -> Response:
        """Make PUT request."""
        return await self.request('PUT', url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> Response:
        """Make DELETE request."""
        return await self.request('DELETE', url, **kwargs)
    
    async def patch(self, url: str, **kwargs) -> Response:
        """Make PATCH request."""
        return await self.request('PATCH', url, **kwargs)
    
    async def head(self, url: str, **kwargs) -> Response:
        """Make HEAD request."""
        return await self.request('HEAD', url, **kwargs)
    
    async def options(self, url: str, **kwargs) -> Response:
        """Make OPTIONS request."""
        return await self.request('OPTIONS', url, **kwargs)
    
    async def gather(self, *requests: tuple[str, str], **kwargs) -> list[Response]:
        """Execute multiple requests concurrently.
        
        This is the recommended way to make multiple requests for maximum performance.
        Instead of sequential requests, this runs them all in parallel.
        
        Args:
            *requests: Tuples of (method, url) or just urls (defaults to GET)
            **kwargs: Common arguments for all requests
            
        Returns:
            List of Response objects
            
        Example:
            responses = await session.gather(
                ('GET', 'https://example.com/1'),
                ('GET', 'https://example.com/2'),
                ('POST', 'https://example.com/3'),
            )
            # Or simply for GET requests:
            responses = await session.gather(
                'https://example.com/1',
                'https://example.com/2',
            )
        """
        tasks = []
        for req in requests:
            if isinstance(req, str):
                tasks.append(self.get(req, **kwargs))
            else:
                method, url = req[0], req[1]
                tasks.append(self.request(method, url, **kwargs))
        
        return await asyncio.gather(*tasks)
    
    async def bulk_get(self, urls: list[str], **kwargs) -> list[Response]:
        """Execute multiple GET requests concurrently.
        
        This is the most efficient way to fetch multiple URLs.
        
        Args:
            urls: List of URLs to fetch
            **kwargs: Common arguments for all requests
            
        Returns:
            List of Response objects
            
        Example:
            urls = [f'https://example.com/{i}' for i in range(100)]
            responses = await session.bulk_get(urls)
        """
        tasks = [self.get(url, **kwargs) for url in urls]
        return await asyncio.gather(*tasks)

    async def close(self) -> None:
        """Close session and all connections."""
        if self._closed:
            return
        self._closed = True
        
        for pool in self._pools.values():
            await pool.close()
        self._pools.clear()
    
    async def __aenter__(self) -> 'Session':
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
    
    def __del__(self) -> None:
        """Cleanup on deletion if session wasn't properly closed."""
        if not self._closed and self._pools:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule cleanup
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except Exception:
                # Best effort cleanup - ignore errors during shutdown
                pass


# Convenience functions for simple one-off requests
# Global session for connection reuse across one-off requests (major speed boost)
_global_session: Optional['Session'] = None


def _get_global_session() -> 'Session':
    """Get or create global session for connection reuse."""
    global _global_session
    if _global_session is None or _global_session._closed:
        _global_session = Session()
    return _global_session


async def request(method: str, url: str, **kwargs) -> Response:
    """Make an HTTP request using global session for connection reuse."""
    return await _get_global_session().request(method, url, **kwargs)


async def get(url: str, **kwargs) -> Response:
    """Make GET request."""
    return await _get_global_session().get(url, **kwargs)


async def post(url: str, **kwargs) -> Response:
    """Make POST request."""
    return await _get_global_session().post(url, **kwargs)


async def put(url: str, **kwargs) -> Response:
    """Make PUT request."""
    return await _get_global_session().put(url, **kwargs)


async def delete(url: str, **kwargs) -> Response:
    """Make DELETE request."""
    return await _get_global_session().delete(url, **kwargs)


async def patch(url: str, **kwargs) -> Response:
    """Make PATCH request."""
    return await _get_global_session().patch(url, **kwargs)


async def head(url: str, **kwargs) -> Response:
    """Make HEAD request."""
    return await _get_global_session().head(url, **kwargs)


async def options(url: str, **kwargs) -> Response:
    """Make OPTIONS request."""
    return await _get_global_session().options(url, **kwargs)
