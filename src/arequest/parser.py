"""High-performance HTTP parsing with optional C-extension support.

Uses httptools when available for faster parsing and falls back to an optimized
pure-Python implementation.
"""

import asyncio
from typing import Optional

# Try to import httptools for C-speed parsing
try:
    import httptools
    HTTPTOOLS_AVAILABLE = True
except ImportError:
    httptools = None
    HTTPTOOLS_AVAILABLE = False


class FastHTTPParser:
    """High-performance HTTP response parser using httptools when available."""
    
    __slots__ = (
        'status_code', 'reason', 'headers', 'body', 'keep_alive',
        '_content_length', '_chunked', '_body_parts', '_headers_complete',
        '_message_complete'
    )
    
    def __init__(self) -> None:
        self.status_code: int = 0
        self.reason: str = ""
        self.headers: dict[str, str] = {}
        self.body: bytes = b""
        self.keep_alive: bool = True
        self._content_length: Optional[int] = None
        self._chunked: bool = False
        self._body_parts: list[bytes] = []
        self._headers_complete: bool = False
        self._message_complete: bool = False
    
    # httptools callbacks
    def on_status(self, status: bytes) -> None:
        self.reason = status.decode('latin-1', errors='replace')
    
    def on_header(self, name: bytes, value: bytes) -> None:
        key = name.decode('latin-1', errors='replace')
        val = value.decode('latin-1', errors='replace')
        self.headers[key] = val
        
        key_lower = key.lower()
        if key_lower == 'content-length':
            self._content_length = int(val)
        elif key_lower == 'transfer-encoding' and 'chunked' in val.lower():
            self._chunked = True
        elif key_lower == 'connection' and 'close' in val.lower():
            self.keep_alive = False
    
    def on_headers_complete(self) -> None:
        self._headers_complete = True
    
    def on_body(self, body: bytes) -> None:
        self._body_parts.append(body)
    
    def on_message_complete(self) -> None:
        self._message_complete = True
        if self._body_parts:
            self.body = b''.join(self._body_parts) if len(self._body_parts) > 1 else self._body_parts[0]
    
    async def parse(self, reader: asyncio.StreamReader) -> None:
        """Parse HTTP response from reader."""
        # Reset state
        self.status_code = 0
        self.reason = ""
        self.headers = {}
        self.body = b""
        self.keep_alive = True
        self._content_length = None
        self._chunked = False
        self._body_parts = []
        self._headers_complete = False
        self._message_complete = False
        
        if HTTPTOOLS_AVAILABLE:
            await self._parse_httptools(reader)
        else:
            await self._parse_python(reader)
    
    async def _parse_httptools(self, reader: asyncio.StreamReader) -> None:
        """Parse using httptools C extension with optimized buffer handling."""
        parser = httptools.HttpResponseParser(self)
        
        # Optimized read loop with larger buffer for better performance
        # 128KB buffer significantly reduces system calls
        while not self._message_complete:
            data = await reader.read(131072)  # 128KB buffer
            if not data:
                break
            parser.feed_data(data)
        
        self.status_code = parser.get_status_code()
        if 'Connection' not in self.headers:
            self.keep_alive = parser.should_keep_alive()
    
    async def _parse_python(self, reader: asyncio.StreamReader) -> None:
        """Pure Python parsing fallback with optimizations."""
        # Read headers with larger buffer hint
        header_bytes = await reader.readuntil(b'\r\n\r\n')
        
        # Parse status line
        status_end = header_bytes.find(b'\r\n')
        status_line = header_bytes[:status_end]
        parts = status_line.split(b' ', 2)
        self.status_code = int(parts[1])
        if len(parts) > 2:
            self.reason = parts[2].decode('latin-1', errors='replace')
        
        # Parse headers with optimized lookup
        # Pre-calculate common header lookups
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
                
                # Use byte comparison for better performance
                kl_bytes = line[:colon].lower()
                if kl_bytes == content_length_key:
                    self._content_length = int(value)
                elif kl_bytes == transfer_encoding_key:
                    if b'chunked' in line[colon+1:].lower():
                        self._chunked = True
                elif kl_bytes == connection_key:
                    if b'close' in line[colon+1:].lower():
                        self.keep_alive = False
        
        # Read body with optimizations
        if self._chunked:
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
        elif self._content_length:
            self.body = await reader.readexactly(self._content_length)


class FastHTTPRequestBuilder:
    """Optimized HTTP request builder with pre-encoded common parts."""
    
    # Pre-encoded constants
    _CRLF = b'\r\n'
    _HTTP11 = b' HTTP/1.1\r\n'
    _COLON_SPACE = b': '
    
    # Pre-encoded common headers
    _COMMON_HEADERS = {
        'Host': b'Host: ',
        'Connection': b'Connection: ',
        'Accept': b'Accept: ',
        'Accept-Encoding': b'Accept-Encoding: ',
        'User-Agent': b'User-Agent: ',
        'Content-Type': b'Content-Type: ',
        'Content-Length': b'Content-Length: ',
        'Authorization': b'Authorization: ',
    }
    
    # Pre-encoded common values
    _COMMON_VALUES = {
        'keep-alive': b'keep-alive',
        '*/*': b'*/*',
        'identity': b'identity',
        'application/json': b'application/json',
        'application/x-www-form-urlencoded': b'application/x-www-form-urlencoded',
    }
    
    # Cache for encoded method bytes
    _METHOD_CACHE = {
        'GET': b'GET',
        'POST': b'POST',
        'PUT': b'PUT',
        'DELETE': b'DELETE',
        'PATCH': b'PATCH',
        'HEAD': b'HEAD',
        'OPTIONS': b'OPTIONS',
    }
    
    @staticmethod
    def build(method: str, path: str, headers: dict[str, str], body: Optional[bytes] = None) -> bytes:
        """Build HTTP request bytes with minimal allocations and maximum caching."""
        # Use cached method or encode
        method_bytes = FastHTTPRequestBuilder._METHOD_CACHE.get(method, method.encode('ascii'))
        
        # Pre-allocate estimated size to reduce reallocations
        estimated_size = len(method_bytes) + len(path) + 20  # method + path + HTTP/1.1\r\n
        # Build request line
        parts = [
            method_bytes,
            b' ',
            path.encode('ascii') if isinstance(path, str) else path,
            FastHTTPRequestBuilder._HTTP11,
        ]
        
        # Optimize header encoding
        for key, value in headers.items():
            header_key = FastHTTPRequestBuilder._COMMON_HEADERS.get(key)
            if header_key:
                parts.append(header_key)
            else:
                parts.append(key.encode('ascii'))
                parts.append(FastHTTPRequestBuilder._COLON_SPACE)
            
            value_bytes = FastHTTPRequestBuilder._COMMON_VALUES.get(value)
            if value_bytes:
                parts.append(value_bytes)
            elif isinstance(value, str):
                parts.append(value.encode('latin-1'))
            else:
                parts.append(value)
            
            parts.append(FastHTTPRequestBuilder._CRLF)
        
        parts.append(FastHTTPRequestBuilder._CRLF)
        
        if body:
            parts.append(body)
        
        return b''.join(parts)
