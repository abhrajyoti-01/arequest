"""Async HTTP client built for speed.

Features:
- Connection pooling with keep-alive
- Concurrent request handling
- C-accelerated parsing (httptools)
- requests-compatible API

Usage:
    import asyncio
    import arequest
    
    async def main():
        r = await arequest.get('https://httpbin.org/get')
        print(r.json())
        
        async with arequest.Session() as s:
            r = await s.get('https://httpbin.org/get')
            print(r.status_code)
    
    asyncio.run(main())
"""

import asyncio
import os
import socket
import ssl
import time
import zlib
from collections import deque
from typing import TYPE_CHECKING, Any, Optional, Union
from urllib.parse import urlencode

if TYPE_CHECKING:
    from .auth import AuthBase

try:
    from .parser import FastHTTPParser, FastHTTPRequestBuilder
    _HAS_FAST_PARSER = True
except ImportError:
    _HAS_FAST_PARSER = False

try:
    import orjson
    _json_dumps = orjson.dumps
    _json_loads = orjson.loads
except ImportError:
    import json as _json
    _json_dumps = lambda x: _json.dumps(x, separators=(',', ':')).encode()
    _json_loads = _json.loads


# Pre-compiled byte constants
_CRLF = b'\r\n'
_CRLFCRLF = b'\r\n\r\n'
_HTTP11 = b' HTTP/1.1\r\n'
_COLON = b':'
_SPACE = b' '
_GZIP_MAGIC = b'\x1f\x8b'


def _decompress(data: bytes, encoding: str) -> bytes:
    if not data:
        return data
    enc = encoding.lower()
    if enc == 'gzip':
        return zlib.decompress(data, zlib.MAX_WBITS | 16)
    if enc == 'deflate':
        try:
            return zlib.decompress(data)
        except zlib.error:
            return zlib.decompress(data, -zlib.MAX_WBITS)
    return data


def _fast_url_parse(url: str):
    """Fast URL parsing - avoids urllib overhead."""
    scheme_end = url.find('://')
    if scheme_end == -1:
        scheme = 'http'
        rest = url
    else:
        scheme = url[:scheme_end]
        rest = url[scheme_end + 3:]
    
    path_start = rest.find('/')
    if path_start == -1:
        host_part = rest
        path = '/'
    else:
        host_part = rest[:path_start]
        path = rest[path_start:]
    
    port_sep = host_part.rfind(':')
    if port_sep != -1 and '[' not in host_part:
        host = host_part[:port_sep]
        try:
            port = int(host_part[port_sep + 1:])
        except ValueError:
            host = host_part
            port = 443 if scheme == 'https' else 80
    else:
        host = host_part
        port = 443 if scheme == 'https' else 80
    
    return scheme, host, port, path


def _gen_boundary():
    import random
    return ''.join(random.choice('0123456789abcdef') for _ in range(32))


def _build_multipart(data: Optional[dict], files: Optional[dict]) -> tuple[bytes, str]:
    """Build multipart form data."""
    boundary = _gen_boundary()
    out = bytearray()
    
    if data:
        for name, val in data.items():
            if val is None:
                continue
            out.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode())
    
    if files:
        for name, info in files.items():
            if isinstance(info, tuple):
                if len(info) < 2:
                    continue
                fname, content = info[0], info[1]
                ctype = info[2] if len(info) > 2 else None
                
                if hasattr(content, 'read'):
                    content = content.read()
                if isinstance(content, str):
                    content = content.encode()
                
                if fname is None:
                    out.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
                    out.extend(content)
                    out.extend(b'\r\n')
                else:
                    if not ctype:
                        ext = os.path.splitext(fname)[1].lower()
                        ctype = {
                            '.txt': 'text/plain', '.json': 'application/json',
                            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                            '.png': 'image/png', '.gif': 'image/gif',
                            '.pdf': 'application/pdf', '.zip': 'application/zip',
                        }.get(ext, 'application/octet-stream')
                    out.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode())
                    out.extend(content)
                    out.extend(b'\r\n')
            elif isinstance(info, bytes):
                out.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
                out.extend(info)
                out.extend(b'\r\n')
            elif isinstance(info, str) and os.path.isfile(info):
                with open(info, 'rb') as f:
                    content = f.read()
                fname = os.path.basename(info)
                out.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
                out.extend(content)
                out.extend(b'\r\n')
            elif hasattr(info, 'read'):
                content = info.read()
                if isinstance(content, str):
                    content = content.encode()
                fname = getattr(info, 'name', name)
                if hasattr(fname, 'rsplit'):
                    fname = fname.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
                out.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
                out.extend(content)
                out.extend(b'\r\n')
    
    out.extend(f'--{boundary}--\r\n'.encode())
    return bytes(out), f'multipart/form-data; boundary={boundary}'


class Response:
    """HTTP response with lazy decoding."""
    
    __slots__ = (
        'status_code', 'headers', 'url', '_body', '_text', '_json',
        'reason', 'elapsed', 'ok', 'encoding', 'cookies', 'history',
        'is_redirect', 'is_permanent_redirect', 'request_info', 'links'
    )
    
    def __init__(self, status_code: int, headers: dict, body: bytes,
                 url: str, reason: str = '', elapsed: float = 0.0):
        self.status_code = status_code
        self.headers = headers
        self.url = url
        self._body = body
        self._text = None
        self._json = None
        self.reason = reason
        self.elapsed = elapsed
        self.ok = status_code < 400
        self.encoding = None
        self.cookies = {}
        self.history = []
        self.is_redirect = status_code in (301, 302, 303, 307, 308)
        self.is_permanent_redirect = status_code in (301, 308)
        self.request_info = None
        self.links = {}
    
    @property
    def content(self) -> bytes:
        return self._body
    
    @property
    def text(self) -> str:
        if self._text is None:
            enc = self.encoding or self._detect_encoding()
            self._text = self._body.decode(enc, errors='replace')
        return self._text
    
    def decode(self, encoding: str = None) -> str:
        if encoding:
            return self._body.decode(encoding, errors='replace')
        return self.text
    
    def json(self) -> Any:
        if self._json is None:
            try:
                self._json = _json_loads(self._body)
            except Exception:
                import json
                try:
                    self._json = json.loads(self.text)
                except json.JSONDecodeError as e:
                    preview = self.text[:200] + ('...' if len(self.text) > 200 else '')
                    raise ValueError(
                        f"Invalid JSON. Status: {self.status_code}, "
                        f"Content-Type: {self.headers.get('Content-Type', '?')}, "
                        f"Preview: {repr(preview)}"
                    ) from e
        return self._json
    
    def _detect_encoding(self) -> str:
        ct = self.headers.get('Content-Type', '')
        if 'charset=' in ct:
            return ct.split('charset=')[-1].split(';')[0].strip()
        return 'utf-8'
    
    def raise_for_status(self):
        if 400 <= self.status_code < 500:
            raise ClientError(f"{self.status_code} Client Error: {self.reason} for {self.url}", self.status_code)
        if self.status_code >= 500:
            raise ServerError(f"{self.status_code} Server Error: {self.reason} for {self.url}", self.status_code)
    
    def iter_content(self, chunk_size: int = 1024):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]
    
    def iter_lines(self, delimiter: bytes = b'\n'):
        for line in self._body.split(delimiter):
            if line:
                yield line
    
    @property
    def apparent_encoding(self) -> str:
        return self._detect_encoding()
    
    def __repr__(self):
        return f"<Response [{self.status_code}]>"
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        pass


class ClientError(Exception):
    def __init__(self, msg: str, status_code: int):
        super().__init__(msg)
        self.status_code = status_code


class ServerError(Exception):
    def __init__(self, msg: str, status_code: int):
        super().__init__(msg)
        self.status_code = status_code


class TimeoutError(Exception):
    pass


class _Pool:
    """Connection pool with fast acquire/release."""
    
    __slots__ = ('host', 'port', 'ssl_ctx', 'max_conns', 'idle_timeout',
                 '_free', '_used', '_closed', '_dns', '_dns_exp')
    
    def __init__(self, host: str, port: int, ssl_ctx=None, max_conns: int = 100):
        self.host = host
        self.port = port
        self.ssl_ctx = ssl_ctx
        self.max_conns = max_conns
        self.idle_timeout = 60.0
        self._free = deque()
        self._used = set()
        self._closed = False
        self._dns = None
        self._dns_exp = 0
    
    async def _resolve(self):
        now = time.monotonic()
        if self._dns and self._dns_exp > now:
            return self._dns
        loop = asyncio.get_running_loop()
        self._dns = await loop.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        self._dns_exp = now + 300
        return self._dns
    
    async def get(self, timeout=None):
        if self._closed:
            raise RuntimeError("Pool closed")
        
        now = time.monotonic()
        while self._free:
            reader, writer, ts = self._free.pop()
            if not writer.is_closing() and (now - ts) < self.idle_timeout:
                self._used.add(writer)
                return reader, writer
            try:
                writer.close()
            except:
                pass
        
        try:
            if timeout:
                reader, writer = await asyncio.wait_for(self._connect(), timeout)
            else:
                reader, writer = await self._connect()
            self._used.add(writer)
            return reader, writer
        except asyncio.TimeoutError:
            raise TimeoutError(f"Connect timeout: {self.host}:{self.port}")
    
    async def _connect(self):
        infos = await self._resolve()
        for family, typ, proto, _, addr in infos:
            try:
                reader, writer = await asyncio.open_connection(
                    addr[0], self.port,
                    ssl=self.ssl_ctx,
                    server_hostname=self.host if self.ssl_ctx else None
                )
                sock = writer.get_extra_info('socket')
                if sock:
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 524288)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 131072)
                    except:
                        pass
                return reader, writer
            except Exception as e:
                last_err = e
        raise last_err
    
    def put(self, reader, writer, keep=True):
        self._used.discard(writer)
        if self._closed or not keep or writer.is_closing():
            try:
                writer.close()
            except:
                pass
            return
        if len(self._free) < self.max_conns:
            self._free.append((reader, writer, time.monotonic()))
        else:
            try:
                writer.close()
            except:
                pass
    
    async def close(self):
        self._closed = True
        for r, w, _ in self._free:
            try:
                w.close()
            except:
                pass
        self._free.clear()
        for w in list(self._used):
            try:
                w.close()
            except:
                pass
        self._used.clear()


class _SimpleParser:
    """Pure Python HTTP parser fallback."""
    
    __slots__ = ('status_code', 'reason', 'headers', 'body', 'keep_alive',
                 '_clen', '_chunked', 'set_cookies')
    
    def __init__(self):
        self.status_code = 0
        self.reason = ''
        self.headers = {}
        self.body = b''
        self.keep_alive = True
        self._clen = None
        self._chunked = False
        self.set_cookies = []
    
    async def parse(self, reader):
        raw = await reader.readuntil(_CRLFCRLF)
        
        status_end = raw.find(_CRLF)
        parts = raw[:status_end].split(_SPACE, 2)
        self.status_code = int(parts[1])
        self.reason = parts[2].decode('latin-1') if len(parts) > 2 else ''
        
        for line in raw[status_end + 2:-4].split(_CRLF):
            if not line:
                break
            sep = line.find(_COLON)
            if sep > 0:
                key = line[:sep].decode('latin-1')
                val = line[sep + 1:].strip().decode('latin-1')
                klow = key.lower()
                
                if klow == 'set-cookie':
                    self.set_cookies.append(val)
                else:
                    self.headers[key] = val
                
                if klow == 'content-length':
                    self._clen = int(val)
                elif klow == 'transfer-encoding' and 'chunked' in val.lower():
                    self._chunked = True
                elif klow == 'connection' and 'close' in val.lower():
                    self.keep_alive = False
        
        if self._chunked:
            await self._read_chunked(reader)
        elif self._clen:
            self.body = await reader.readexactly(self._clen)
    
    async def _read_chunked(self, reader):
        parts = []
        while True:
            line = await reader.readline()
            size = int(line.strip().split(b';')[0], 16)
            if size == 0:
                await reader.readline()
                break
            parts.append(await reader.readexactly(size))
            await reader.readexactly(2)
        self.body = b''.join(parts)


class _SimpleBuilder:
    """Simple HTTP request builder."""
    
    @staticmethod
    def build(method: str, path: str, headers: dict, body: bytes = None) -> bytes:
        out = bytearray()
        out.extend(method.encode())
        out.extend(b' ')
        out.extend(path.encode() if isinstance(path, str) else path)
        out.extend(_HTTP11)
        for k, v in headers.items():
            out.extend(k.encode())
            out.extend(b': ')
            out.extend(v.encode('latin-1') if isinstance(v, str) else v)
            out.extend(_CRLF)
        out.extend(_CRLF)
        if body:
            out.extend(body)
        return bytes(out)


# Shared SSL contexts
_SSL_VERIFIED = None
_SSL_UNVERIFIED = None


def _get_ssl(verify=True):
    global _SSL_VERIFIED, _SSL_UNVERIFIED
    if verify:
        if _SSL_VERIFIED is None:
            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            _SSL_VERIFIED = ctx
        return _SSL_VERIFIED
    else:
        if _SSL_UNVERIFIED is None:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            _SSL_UNVERIFIED = ctx
        return _SSL_UNVERIFIED


class Session:
    """High-performance HTTP session.
    
    Drop-in async replacement for requests.Session with:
    - Connection pooling
    - DNS caching (5 min)
    - Cookie persistence
    - Keep-alive
    
    Example:
        async with Session() as s:
            r = await s.get('https://example.com')
            print(r.text)
    """
    
    __slots__ = (
        '_pools', '_headers', '_timeout', '_closed', '_max_per_host',
        'auth', 'cookies', 'verify', 'proxies', 'hooks', 'params',
        'stream', 'cert', 'max_redirects', 'trust_env',
        '_parser_cls', '_builder_cls', '_cookie_str', '_cookie_dirty'
    )
    
    _SSL_VERIFIED = None
    _SSL_UNVERIFIED = None
    
    def __init__(self, headers=None, timeout=None, connector_limit=100,
                 connector_limit_per_host=50, auth=None, verify=True):
        self._pools = {}
        self._headers = headers.copy() if headers else {}
        self._timeout = timeout
        self._closed = False
        self._max_per_host = connector_limit_per_host
        self.auth = auth
        self.cookies = {}
        self.verify = verify
        self.proxies = {}
        self.hooks = {}
        self.params = {}
        self.stream = False
        self.cert = None
        self.max_redirects = 30
        self.trust_env = True
        self._cookie_str = ''
        self._cookie_dirty = True
        
        if _HAS_FAST_PARSER:
            self._parser_cls = FastHTTPParser
            self._builder_cls = FastHTTPRequestBuilder
        else:
            self._parser_cls = _SimpleParser
            self._builder_cls = _SimpleBuilder
    
    @property
    def headers(self):
        return self._headers
    
    @headers.setter
    def headers(self, val):
        self._headers = val.copy() if val else {}
    
    def _pool(self, host, port, is_ssl, verify):
        key = (host, port, is_ssl)
        if key not in self._pools:
            ctx = _get_ssl(verify) if is_ssl else None
            self._pools[key] = _Pool(host, port, ctx, self._max_per_host)
        return self._pools[key]
    
    def _cookie_header(self):
        if self._cookie_dirty:
            self._cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
            self._cookie_dirty = False
        return self._cookie_str
    
    def _store_cookies(self, cookies):
        if not cookies:
            return
        for c in cookies:
            sep = c.find(';')
            pair = c[:sep] if sep > 0 else c
            eq = pair.find('=')
            if eq > 0:
                self.cookies[pair[:eq].strip()] = pair[eq + 1:].strip()
        self._cookie_dirty = True
    
    async def request(self, method: str, url: str, *, headers=None, params=None,
                      data=None, json=None, files=None, timeout=None, verify=None,
                      allow_redirects=True, max_redirects=10, auth=None) -> Response:
        if self._closed:
            raise RuntimeError("Session closed")
        
        t0 = time.perf_counter()
        
        scheme, host, port, path = _fast_url_parse(url)
        
        if params:
            sep = '&' if '?' in path else '?'
            path = f"{path}{sep}{urlencode(params)}"
        
        is_ssl = scheme == 'https'
        do_verify = verify if verify is not None else self.verify
        
        hdrs = {**self._headers, **headers} if headers else self._headers.copy()
        hdr_low = {k.lower(): k for k in hdrs}
        
        def has_hdr(name):
            return name.lower() in hdr_low
        
        def set_hdr(name, val, force=False):
            low = name.lower()
            if low in hdr_low and not force:
                return
            if low in hdr_low:
                del hdrs[hdr_low[low]]
            hdrs[name] = val
            hdr_low[low] = name
        
        host_val = host if port in (80, 443) else f"{host}:{port}"
        set_hdr('Host', host_val)
        set_hdr('Connection', 'keep-alive')
        set_hdr('Accept-Encoding', 'gzip, deflate')
        set_hdr('User-Agent', 'Mozilla/5.0 (compatible; arequest/1.2)')
        
        if self.cookies and not has_hdr('Cookie'):
            ck = self._cookie_header()
            if ck:
                set_hdr('Cookie', ck)
        
        req_auth = auth or self.auth
        if req_auth and hasattr(req_auth, 'apply'):
            class _R:
                pass
            _R.headers = hdrs
            req_auth.apply(_R())
        
        body = None
        if files is not None:
            body, ct = _build_multipart(data if isinstance(data, dict) else None, files)
            set_hdr('Content-Type', ct, force=True)
            set_hdr('Accept', '*/*')
        elif json is not None:
            body = _json_dumps(json)
            set_hdr('Content-Type', 'application/json', force=True)
            set_hdr('Accept', 'application/json', force=True)
        elif data is not None:
            if isinstance(data, dict):
                body = urlencode(data).encode()
                set_hdr('Content-Type', 'application/x-www-form-urlencoded')
            elif isinstance(data, str):
                body = data.encode()
                set_hdr('Content-Type', 'text/plain; charset=utf-8')
            else:
                body = data
            set_hdr('Accept', '*/*')
        else:
            set_hdr('Accept', '*/*')
        
        if body:
            set_hdr('Content-Length', str(len(body)), force=True)
            if method.upper() in ('POST', 'PUT', 'PATCH'):
                origin = f"{scheme}://{host}" if port in (80, 443) else f"{scheme}://{host}:{port}"
                set_hdr('Origin', origin)
        
        req_bytes = self._builder_cls.build(method.upper(), path, hdrs, body)
        
        pool = self._pool(host, port, is_ssl, do_verify)
        tout = timeout or self._timeout
        
        reader = writer = None
        try:
            reader, writer = await pool.get(tout)
            writer.write(req_bytes)
            await writer.drain()
            
            parser = self._parser_cls()
            await parser.parse(reader)
            
            elapsed = time.perf_counter() - t0
            
            resp_body = parser.body
            enc = parser.headers.get('Content-Encoding', '')
            
            if enc:
                try:
                    resp_body = _decompress(resp_body, enc)
                except:
                    pass
            elif resp_body and len(resp_body) >= 2 and resp_body[:2] == _GZIP_MAGIC:
                try:
                    resp_body = _decompress(resp_body, 'gzip')
                except:
                    pass
            
            resp = Response(
                status_code=parser.status_code,
                headers=parser.headers,
                body=resp_body,
                url=url,
                reason=parser.reason,
                elapsed=elapsed
            )
            
            self._store_cookies(parser.set_cookies)
            pool.put(reader, writer, parser.keep_alive)
            reader = writer = None
            
            if allow_redirects and resp.status_code in (301, 302, 303, 307, 308):
                if max_redirects > 0:
                    loc = resp.headers.get('Location', '')
                    if loc:
                        if not loc.startswith('http'):
                            loc = f"{scheme}://{host}:{port}{loc}"
                        new_method = 'GET' if resp.status_code == 303 else method
                        return await self.request(
                            new_method, loc,
                            headers=headers, timeout=timeout, verify=verify,
                            allow_redirects=True, max_redirects=max_redirects - 1
                        )
            
            return resp
            
        except asyncio.TimeoutError:
            if reader and writer:
                pool.put(reader, writer, False)
            raise TimeoutError(f"Timeout: {url}")
        except Exception:
            if reader and writer:
                pool.put(reader, writer, False)
            raise
    
    async def get(self, url, **kw):
        return await self.request('GET', url, **kw)
    
    async def post(self, url, **kw):
        return await self.request('POST', url, **kw)
    
    async def put(self, url, **kw):
        return await self.request('PUT', url, **kw)
    
    async def delete(self, url, **kw):
        return await self.request('DELETE', url, **kw)
    
    async def patch(self, url, **kw):
        return await self.request('PATCH', url, **kw)
    
    async def head(self, url, **kw):
        return await self.request('HEAD', url, **kw)
    
    async def options(self, url, **kw):
        return await self.request('OPTIONS', url, **kw)
    
    async def gather(self, *reqs, **kw):
        """Run multiple requests concurrently."""
        tasks = []
        for r in reqs:
            if isinstance(r, str):
                tasks.append(self.get(r, **kw))
            else:
                tasks.append(self.request(r[0], r[1], **kw))
        return await asyncio.gather(*tasks)
    
    async def bulk_get(self, urls, **kw):
        """Fetch multiple URLs concurrently."""
        return await asyncio.gather(*[self.get(u, **kw) for u in urls])
    
    async def close(self):
        if self._closed:
            return
        self._closed = True
        for p in self._pools.values():
            await p.close()
        self._pools.clear()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    def __del__(self):
        if not self._closed and self._pools:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except:
                pass


_session = None


def _get_session():
    global _session
    if _session is None or _session._closed:
        _session = Session()
    return _session


async def request(method, url, **kw):
    return await _get_session().request(method, url, **kw)


async def get(url, **kw):
    return await _get_session().get(url, **kw)


async def post(url, **kw):
    return await _get_session().post(url, **kw)


async def put(url, **kw):
    return await _get_session().put(url, **kw)


async def delete(url, **kw):
    return await _get_session().delete(url, **kw)


async def patch(url, **kw):
    return await _get_session().patch(url, **kw)


async def head(url, **kw):
    return await _get_session().head(url, **kw)


async def options(url, **kw):
    return await _get_session().options(url, **kw)
