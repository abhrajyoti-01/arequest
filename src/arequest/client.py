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
import ssl
import time
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
            # Use orjson if available for faster JSON decoding, fallback to standard json
            try:
                import orjson
                self._json_data = orjson.loads(self._body)
            except ImportError:
                import json
                self._json_data = json.loads(self.text)
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
    """High-performance connection pool for a single host."""
    
    __slots__ = (
        'host', 'port', 'ssl_context', 'max_size', 'max_idle_time',
        '_available', '_in_use', '_closed', '_dns_cache',
        '_dns_expire', '_creating'
    )
    
    def __init__(
        self,
        host: str,
        port: int,
        ssl_context: Optional[ssl.SSLContext] = None,
        max_size: int = 100,
        max_idle_time: float = 30.0,
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
    
    async def _resolve_dns(self) -> list[tuple]:
        """Resolve and cache DNS."""
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
        self._dns_expire = now + 60.0
        return infos
    
    async def acquire(self, timeout: Optional[float] = None) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Get a connection from pool or create new one with optimized logic."""
        if self._closed:
            raise RuntimeError("Pool is closed")
        
        now = time.monotonic()
        # Optimize: iterate in reverse for LRU-like behavior (newer connections first)
        while self._available:
            try:
                reader, writer, created = self._available.pop(0)
                # Fast path: check if connection is still valid
                if not writer.is_closing() and (now - created) <= self.max_idle_time:
                    self._in_use.add(writer)
                    return reader, writer
                # Close stale connection
                if not writer.is_closing():
                    writer.close()
            except IndexError:
                break
        
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
                
                # Optimize socket for low latency
                sock = writer.get_extra_info('socket')
                if sock:
                    try:
                        import socket
                        # Disable Nagle's algorithm for lower latency
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        # Enable TCP keepalive for connection health
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        # Set larger socket buffers for better throughput
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)  # 256KB
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)  # 256KB
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
    
    __slots__ = ('status_code', 'reason', 'headers', 'body', 'keep_alive', '_content_length', '_chunked')
    
    def __init__(self):
        self.status_code = 0
        self.reason = ""
        self.headers = {}
        self.body = b""
        self.keep_alive = True
        self._content_length = None
        self._chunked = False
    
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
        
        for line in header_bytes[status_end+2:-4].split(b'\r\n'):
            if not line:
                break
            colon = line.find(b':')
            if colon > 0:
                key = line[:colon].decode('latin-1')
                value = line[colon+1:].strip().decode('latin-1')
                self.headers[key] = value
                
                kl_bytes = line[:colon].lower()
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
    """High-performance HTTP session with full requests.Session API compatibility.
    
    Drop-in async replacement for requests.Session with connection pooling and optimizations.
    
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
        'trust_env'
    )
    
    def __init__(
        self,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        connector_limit: int = 100,
        connector_limit_per_host: int = 30,
        auth: "Optional[AuthBase]" = None,
        verify: bool = True,
    ):
        """Initialize session with optimized defaults (requests-compatible API).
        
        Args:
            headers: Default headers for all requests
            timeout: Default timeout in seconds
            connector_limit: Total connection limit
            connector_limit_per_host: Per-host connection limit
            auth: Default authentication
            verify: SSL verification (default True)
        """
        self._pools: dict[tuple[str, int, bool], _ConnectionPool] = {}
        # Use empty dict as default for better performance
        self._default_headers = headers.copy() if headers else {}
        self._default_timeout = timeout
        self._ssl_contexts: dict[bool, ssl.SSLContext] = {}
        self._closed = False
        self._connector_limit = connector_limit
        self._connector_limit_per_host = connector_limit_per_host
        self.auth = auth
        self.cookies: dict[str, str] = {}
        self.verify = verify
        
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
    
    def _get_ssl_context(self, verify: bool = True) -> Optional[ssl.SSLContext]:
        """Get cached SSL context."""
        if verify not in self._ssl_contexts:
            if verify:
                ctx = ssl.create_default_context()
            else:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            self._ssl_contexts[verify] = ctx
        return self._ssl_contexts[verify]
    
    def _get_pool(self, host: str, port: int, is_ssl: bool, verify: bool = True) -> _ConnectionPool:
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
        
        parsed = urlparse(url)
        scheme = parsed.scheme
        host = parsed.hostname or ''
        port = parsed.port or (443 if scheme == 'https' else 80)
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        
        if params:
            sep = '&' if '?' in path else '?'
            path += sep + urlencode(params)
        
        is_ssl = scheme == 'https'
        verify_ssl = verify if verify is not None else self.verify
        
        # Optimize header merging - start with defaults and only update if needed
        if headers:
            req_headers = {**self._default_headers, **headers}
        else:
            req_headers = self._default_headers.copy()
        
        # Set required headers only if not present (optimized checks)
        if 'Host' not in req_headers:
            req_headers['Host'] = host if port in (80, 443) else f"{host}:{port}"
        if 'Connection' not in req_headers:
            req_headers['Connection'] = 'keep-alive'
        if 'Accept' not in req_headers:
            req_headers['Accept'] = '*/*'
        if 'Accept-Encoding' not in req_headers:
            req_headers['Accept-Encoding'] = 'identity'
        if 'User-Agent' not in req_headers:
            req_headers['User-Agent'] = 'arequest/0.2.0'
        
        request_auth = auth or self.auth
        if request_auth and hasattr(request_auth, 'apply'):
            class _TempReq:
                headers = req_headers
            request_auth.apply(_TempReq())
        
        body: Optional[bytes] = None
        if json is not None:
            # Use orjson if available for faster JSON encoding, fallback to standard json
            try:
                import orjson
                body = orjson.dumps(json)
            except ImportError:
                import json as json_module
                body = json_module.dumps(json, separators=(',', ':')).encode('utf-8')
            req_headers['Content-Type'] = 'application/json'
        elif data is not None:
            if isinstance(data, dict):
                body = urlencode(data).encode('utf-8')
                req_headers['Content-Type'] = 'application/x-www-form-urlencoded'
            elif isinstance(data, str):
                body = data.encode('utf-8')
            else:
                body = data
        
        if body:
            req_headers['Content-Length'] = str(len(body))
        
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
            
            response = Response(
                status_code=parser.status_code,
                headers=parser.headers,
                body=parser.body,
                url=url,
                reason=parser.reason,
                elapsed=elapsed,
            )
            
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


# Convenience functions for simple one-off requests
async def request(method: str, url: str, **kwargs) -> Response:
    """Make an HTTP request."""
    async with Session() as session:
        return await session.request(method, url, **kwargs)


async def get(url: str, **kwargs) -> Response:
    """Make GET request."""
    async with Session() as session:
        return await session.get(url, **kwargs)


async def post(url: str, **kwargs) -> Response:
    """Make POST request."""
    async with Session() as session:
        return await session.post(url, **kwargs)


async def put(url: str, **kwargs) -> Response:
    """Make PUT request."""
    async with Session() as session:
        return await session.put(url, **kwargs)


async def delete(url: str, **kwargs) -> Response:
    """Make DELETE request."""
    async with Session() as session:
        return await session.delete(url, **kwargs)


async def patch(url: str, **kwargs) -> Response:
    """Make PATCH request."""
    async with Session() as session:
        return await session.patch(url, **kwargs)


async def head(url: str, **kwargs) -> Response:
    """Make HEAD request."""
    async with Session() as session:
        return await session.head(url, **kwargs)


async def options(url: str, **kwargs) -> Response:
    """Make OPTIONS request."""
    async with Session() as session:
        return await session.options(url, **kwargs)
