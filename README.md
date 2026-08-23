# arequest

**Fast async HTTP client for Python with real browser fingerprints.**

[![PyPI version](https://badge.fury.io/py/arequest.svg)](https://badge.fury.io/py/arequest)
[![Python versions](https://img.shields.io/pypi/pyversions/arequest.svg)](https://pypi.org/project/arequest/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

`arequest` combines a [requests](https://requests.readthedocs.io/)-style API with
[curl-impersonate](https://github.com/lwthiker/curl-impersonate) powered browser
impersonation. Requests go out over `asyncio` through libcurl's multiplexed
connection engine, carrying a byte-exact browser fingerprint on every layer:

| Layer | What matches a real browser |
|---|---|
| TLS | ClientHello ciphers/extensions/order → **JA3 / JA4** hashes |
| HTTP/2 | SETTINGS, WINDOW_UPDATE, priorities → **Akamai** fingerprint |
| Headers | Full `sec-ch-ua`, `sec-fetch-*`, header order and casing |

Verified against [tls.peet.ws](https://tls.peet.ws) - impersonating `chrome`
produces Chrome's exact JA4 (`t13d1516h2_8daaf6152771_d8a2da3f94cd`) and Akamai
fingerprints.

---

## Why arequest

- **Undetectable by default** - sessions impersonate the latest Chrome unless told otherwise
- **Requests-like syntax** - `Session`, `get/post/put/delete/...`, familiar kwargs
- **Async-native** - built on `asyncio`; no thread pools, no blocking calls
- **Fast** - libcurl multi-connection pooling, keep-alive, HTTP/2 multiplexing
- **Stable under load** - per-host connection limits, retries with backoff, rate limiting
- **Batteries included** - cookies, redirects, proxies, streaming, auth, hooks

---

## Installation

```bash
pip install arequest
```

> **Windows:** for best performance, run your event loop with the selector
> policy: `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())`

---

## Quick Start

### Simple request

```python
import asyncio
import arequest

async def main():
    response = await arequest.get("https://httpbin.org/get")
    print(response.status_code)
    print(response.json())

asyncio.run(main())
```

### Session with impersonation (recommended)

```python
import asyncio
import arequest

async def main():
    async with arequest.Session(impersonate="chrome") as session:
        response = await session.get("https://tls.peet.ws/api/all")
        data = response.json()
        print("JA4:", data["tls"]["ja4"])          # identical to real Chrome
        print("HTTP/2:", data["http_version"])     # h2

asyncio.run(main())
```

### Concurrent requests

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        urls = [f"https://httpbin.org/get?i={i}" for i in range(100)]
        responses = await session.bulk_get(urls)
        print(f"{sum(r.ok for r in responses)}/{len(responses)} succeeded")

asyncio.run(main())
```

---

## Browser Impersonation

Pass an `impersonate` profile to make requests indistinguishable from that
browser at the TLS and HTTP layers.

```python
# Session-wide
session = arequest.Session(impersonate="chrome")

# Per-request override
await session.get(url, impersonate="safari184")

# Disable impersonation entirely
session = arequest.Session(impersonate=None)
```

List available profiles:

```python
print(arequest.available_profiles())   # ('chrome', 'chrome100', ..., 'safari184', ...)
```

Aliases like `"latest"`, `"chrome_android"`, `"safari_ios"` also work.

### Advanced fingerprint control

Power users can supply raw fingerprints instead of profiles:

```python
response = await arequest.get(
    url,
    ja3="771,4865-4866-4867-49195-49199-...,0-23-65281-...,29-23-24,0",
    akamai="1:65536;2:0;4:6291456;6:262144|15663105|0|m,a,s,p",
    extra_fp={"tls_signature_algorithms": ["ecdsa_secp256r1_sha256", ...]},
)
```

Verify any setup against a live echo endpoint:

```python
r = await arequest.get("https://tls.peet.ws/api/all")
r.json()["tls"]["ja3_hash"]      # server-observed JA3
r.json()["http2"]["akamai_fingerprint_hash"]
```

---

## Usage Guide

### All HTTP methods

```python
async with arequest.Session() as s:
    await s.get(url)
    await s.post(url, json={"key": "value"})
    await s.put(url, data="raw body")
    await s.patch(url, json={"update": "field"})
    await s.delete(url)
    await s.head(url)
    await s.options(url)
```

### Query params, headers, forms, files

```python
await s.get(url, params={"page": 2, "limit": 10})
await s.get(url, headers={"Authorization": "Bearer <token>"})
await s.post(url, data={"username": "user", "password": "pass"})
await s.post(url, files={"upload": ("report.pdf", pdf_bytes, "application/pdf")})
```

### Cookies

```python
async with arequest.Session() as s:
    await s.get("https://httpbin.org/cookies/set/session/persisted")
    r = await s.get("https://httpbin.org/cookies")   # cookie sent automatically
    print(s.cookies)
```

### Authentication

```python
from arequest import BasicAuth, BearerAuth

await arequest.get(url, auth=BasicAuth("user", "pass"))
await arequest.get(url, auth=BearerAuth("<token>"))
```

Custom schemes: subclass `arequest.AuthBase` and implement `apply(request)`.

### Proxies

```python
session = arequest.Session(proxies={"https": "http://proxy:8080"})
# or per-request
await session.get(url, proxy="socks5://user:pass@host:1080")
```

Environment proxies (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`) are honored by default.

### Retries with backoff

```python
session = arequest.Session(retries=3, backoff=0.5)
# or fine-grained control
from arequest import RetryPolicy

policy = RetryPolicy(
    total=5,                      # max retries per request
    backoff_factor=0.5,           # exponential base delay
    status_forcelist=frozenset((429, 500, 502, 503, 504)),
)
session = arequest.Session(retries=policy)
```

Retries honor `Retry-After` headers and only replay idempotent methods by default.

### Rate limiting

```python
session = arequest.Session(rate_limit=20.0, rate_limit_per_host=10.0)
```

### Streaming responses

```python
async with arequest.Session(stream=True) as s:
    async with await s.get(large_file_url) as r:
        async for chunk in r.aiter_content(chunk_size=65536):
            process(chunk)
```

### Bounded concurrent fetching

```python
# Yields responses as they complete, never more than 20 in flight
async for r in session.iter_fetch(urls, max_concurrency=20):
    print(r.status_code)
```

### WebSockets

```python
async with arequest.Session(impersonate="chrome") as session:
    handle = await session.ws_connect("wss://example.com/socket")
    async with handle as ws:
        await ws.send_json({"type": "subscribe"})
        while True:
            message = await ws.recv_json()
            handle_message(message)
```

WebSocket connections carry the same browser fingerprint as HTTP requests.

### Proxy pools

```python
pool = arequest.ProxyPool(
    ["socks5://user:pass@p1:1080", "http://p2:8080", "http://p3:8080"],
    strategy="round_robin",   # or "random" / "failover"
    cooldown=300.0,           # seconds to skip a failing proxy
)
session = arequest.Session(proxy_pool=pool)

print(pool.status())   # {'socks5://...': True, 'http://p2:8080': False, ...}
```

Failed proxies are automatically put on cooldown and retried later.

### Session persistence

```python
# Save cookies + settings to resume later
await session.save("state.json")

# Restore exactly where you left off
session = await arequest.Session.load("state.json")
```

### Redirect control

```python
await s.get(url, allow_redirects=False)       # don't follow
await s.get(url, max_redirects=5)             # custom limit
r.history                                     # intermediate responses
```

### Timeouts

```python
await s.get(url, timeout=5.0)                       # total seconds
await s.get(url, timeout=(3.0, 10.0))               # connect, read
```

### Error handling

```python
try:
    r = await s.get("https://httpbin.org/status/404")
    r.raise_for_status()
except arequest.ClientError as e:
    print(f"client error: {e.status_code}")
except arequest.ServerError as e:
    print(f"server error: {e.status_code}")
except arequest.TimeoutError:
    print("timed out")
except arequest.ConnectionError:
    print("connection failed")
```

Exception hierarchy: `RequestError` → `TransportError` (`ConnectionError`,
`TimeoutError`, `ProxyError`, `SSLError`) / `HTTPError` (`ClientError`,
`ServerError`) / `InvalidURL` / `TooManyRedirects` / `ImpersonationError`.

---

## API Overview

### Response

```python
r.status_code      # int
r.ok               # bool - status < 400
r.headers          # case-insensitive dict
r.content          # bytes
r.text             # str
r.json()           # parsed body
r.encoding         # detected / forced encoding
r.url              # final URL after redirects
r.elapsed          # seconds
r.cookies          # cookies received with this response
r.history          # redirect chain
r.is_redirect      # bool - 3xx with Location header
r.attempts         # attempts used (retries included)
r.raise_for_status()
r.aclose()         # release body / connection early
r.aiter_content()  # async streaming
r.aiter_lines()    # async line iterator
```

### Session options

```python
session = arequest.Session(
    headers={"User-Agent": "my-app"},   # merged over impersonation defaults
    timeout=30.0,
    connector_limit=100,
    connector_limit_per_host=0,
    verify=True,
    impersonate="chrome",
    http_version="auto",                # auto | h1 | h2 | h3
    retries=0,
    backoff=None,
)
```

Every option can be overridden per request.

### Top-level helpers

`arequest.request(method, url, ...)`, `get`, `post`, `put`, `patch`, `delete`,
`head`, `options`, `aclose()` - each uses an implicit per-loop session.

---

## Performance Notes

- Connections are pooled per origin and reused across requests (keep-alive).
- HTTP/2 is negotiated automatically where supported; one multiplexed
  connection serves many concurrent requests.
- Tune `connector_limit` / `connector_limit_per_host` for your workload.
- On Linux/macOS, `pip install arequest[uvloop]` speeds up the event loop.

Benchmarks live in [`tests/benchmarks/`](tests/benchmarks/).

---

## Development

```bash
git clone https://github.com/abhrajyoti-01/arequest.git
cd arequest
pip install -e .[dev]

pytest                # run tests
ruff check src/ tests/
ruff format src/      # format
```

---

## License

MIT - see [LICENSE](LICENSE).

## Author

**Abhra** - [@abhrajyoti-01](https://github.com/abhrajyoti-01)
