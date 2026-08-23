# arequest Documentation

**arequest** is a fast async HTTP client with a `requests`-like API and real
browser impersonation (TLS JA3/JA4 + HTTP/2 Akamai fingerprints) powered by
curl-impersonate.

## Quick Start

```bash
pip install arequest
```

```python
import asyncio
import arequest

async def main():
    # One-off request with Chrome's exact fingerprint
    r = await arequest.get("https://tls.peet.ws/api/all", impersonate="chrome")
    print(r.json()["tls"]["ja4"])

    # Session reuse across many requests
    async with arequest.Session(impersonate="chrome") as session:
        r = await session.get("https://httpbin.org/get")
        print(r.status_code, r.json())

asyncio.run(main())
```

## Documentation

- [API Reference](api.md) - classes, functions and exceptions
- [Client Guide](client.md) - Session lifecycle, requests, responses, streaming
- [Authentication](auth.md) - Basic/Bearer auth and custom handlers

## Features

- **Browser impersonation** - byte-exact TLS and HTTP/2 fingerprints per browser profile
- **Requests-like API** - familiar `Session`, `get/post/...`, kwargs and exceptions
- **Async-native** - coroutine-based client on top of libcurl's connection engine
- **Connection pooling** - keep-alive reuse with global and per-host limits
- **Reliability tools** - retries with backoff, rate limiting, redirect control
- **Streaming** - `aiter_content` / `aiter_lines` for large bodies

## Installation

```bash
pip install arequest
```

Optional extras:

```bash
pip install arequest[uvloop]   # faster event loop on Linux/macOS
```

Development:

```bash
git clone https://github.com/abhrajyoti-01/arequest.git
cd arequest
pip install -e .[dev]
pytest
```

## License

MIT - see [LICENSE](../LICENSE).
