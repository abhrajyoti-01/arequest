"""HTTP parsing with httptools C extension.

Uses httptools for blazing fast parsing, falls back to optimized
pure-Python parser if unavailable.
"""

import asyncio
from typing import Optional

try:
    import httptools
    HTTPTOOLS_AVAILABLE = True
except ImportError:
    httptools = None
    HTTPTOOLS_AVAILABLE = False

# Pre-compiled constants
_CRLF = b'\r\n'
_COLON = b':'


class FastHTTPParser:
    """HTTP parser using httptools C extension."""
    
    __slots__ = (
        'status_code', 'reason', 'headers', 'body', 'keep_alive',
        '_clen', '_chunked', '_parts', '_hdone', '_done', 'set_cookies'
    )
    
    def __init__(self):
        self.status_code = 0
        self.reason = ''
        self.headers = {}
        self.body = b''
        self.keep_alive = True
        self._clen = None
        self._chunked = False
        self._parts = []
        self._hdone = False
        self._done = False
        self.set_cookies = []
    
    def on_status(self, status: bytes):
        self.reason = status.decode('latin-1', errors='replace')
    
    def on_header(self, name: bytes, value: bytes):
        k = name.decode('latin-1', errors='replace')
        v = value.decode('latin-1', errors='replace')
        kl = k.lower()
        
        if kl == 'set-cookie':
            self.set_cookies.append(v)
        else:
            self.headers[k] = v
        
        if kl == 'content-length':
            self._clen = int(v)
        elif kl == 'transfer-encoding' and 'chunked' in v.lower():
            self._chunked = True
        elif kl == 'connection' and 'close' in v.lower():
            self.keep_alive = False
    
    def on_headers_complete(self):
        self._hdone = True
    
    def on_body(self, data: bytes):
        self._parts.append(data)
    
    def on_message_complete(self):
        self._done = True
        if self._parts:
            self.body = b''.join(self._parts) if len(self._parts) > 1 else self._parts[0]
    
    async def parse(self, reader: asyncio.StreamReader):
        self.status_code = 0
        self.reason = ''
        self.headers = {}
        self.body = b''
        self.keep_alive = True
        self._clen = None
        self._chunked = False
        self._parts = []
        self._hdone = False
        self._done = False
        self.set_cookies = []
        
        if HTTPTOOLS_AVAILABLE:
            await self._parse_fast(reader)
        else:
            await self._parse_py(reader)
    
    async def _parse_fast(self, reader):
        parser = httptools.HttpResponseParser(self)
        
        # Big initial read - usually gets headers + body start
        chunk = await reader.read(65536)
        if chunk:
            parser.feed_data(chunk)
        
        while not self._done:
            chunk = await reader.read(262144)
            if not chunk:
                break
            parser.feed_data(chunk)
        
        self.status_code = parser.get_status_code()
        if 'Connection' not in self.headers:
            self.keep_alive = parser.should_keep_alive()
    
    async def _parse_py(self, reader):
        raw = await reader.readuntil(b'\r\n\r\n')
        
        idx = raw.find(_CRLF)
        parts = raw[:idx].split(b' ', 2)
        self.status_code = int(parts[1])
        if len(parts) > 2:
            self.reason = parts[2].decode('latin-1', errors='replace')
        
        for line in raw[idx + 2:-4].split(_CRLF):
            if not line:
                break
            sep = line.find(_COLON)
            if sep > 0:
                k = line[:sep].decode('latin-1')
                v = line[sep + 1:].strip().decode('latin-1')
                kl = k.lower()
                
                if kl == 'set-cookie':
                    self.set_cookies.append(v)
                else:
                    self.headers[k] = v
                
                if kl == 'content-length':
                    self._clen = int(v)
                elif kl == 'transfer-encoding' and 'chunked' in v.lower():
                    self._chunked = True
                elif kl == 'connection' and 'close' in v.lower():
                    self.keep_alive = False
        
        if self._chunked:
            parts = []
            while True:
                line = await reader.readline()
                sz = int(line.strip().split(b';')[0], 16)
                if sz == 0:
                    await reader.readline()
                    break
                parts.append(await reader.readexactly(sz))
                await reader.readexactly(2)
            self.body = b''.join(parts)
        elif self._clen:
            self.body = await reader.readexactly(self._clen)


class FastHTTPRequestBuilder:
    """Fast HTTP request builder with caching."""
    
    _CRLF = b'\r\n'
    _HTTP11 = b' HTTP/1.1\r\n'
    _SEP = b': '
    
    _METHODS = {
        'GET': b'GET', 'POST': b'POST', 'PUT': b'PUT',
        'DELETE': b'DELETE', 'PATCH': b'PATCH',
        'HEAD': b'HEAD', 'OPTIONS': b'OPTIONS'
    }
    
    _HEADERS = {
        'Host': b'Host: ', 'Connection': b'Connection: ',
        'Accept': b'Accept: ', 'Accept-Encoding': b'Accept-Encoding: ',
        'User-Agent': b'User-Agent: ', 'Content-Type': b'Content-Type: ',
        'Content-Length': b'Content-Length: ', 'Authorization': b'Authorization: ',
        'Cookie': b'Cookie: ', 'Origin': b'Origin: '
    }
    
    _VALUES = {
        'keep-alive': b'keep-alive', '*/*': b'*/*',
        'application/json': b'application/json',
        'application/x-www-form-urlencoded': b'application/x-www-form-urlencoded',
        'gzip, deflate': b'gzip, deflate'
    }
    
    @staticmethod
    def build(method: str, path: str, headers: dict, body: bytes = None) -> bytes:
        out = bytearray()
        
        # Method
        m = FastHTTPRequestBuilder._METHODS.get(method)
        out.extend(m if m else method.encode())
        out.extend(b' ')
        
        # Path
        out.extend(path.encode() if isinstance(path, str) else path)
        out.extend(FastHTTPRequestBuilder._HTTP11)
        
        # Headers
        for k, v in headers.items():
            hk = FastHTTPRequestBuilder._HEADERS.get(k)
            if hk:
                out.extend(hk)
            else:
                out.extend(k.encode())
                out.extend(FastHTTPRequestBuilder._SEP)
            
            hv = FastHTTPRequestBuilder._VALUES.get(v)
            if hv:
                out.extend(hv)
            elif isinstance(v, str):
                out.extend(v.encode('latin-1'))
            else:
                out.extend(v)
            
            out.extend(FastHTTPRequestBuilder._CRLF)
        
        out.extend(FastHTTPRequestBuilder._CRLF)
        
        if body:
            out.extend(body)
        
        return bytes(out)
