# Changelog

All notable changes to `arequest` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.2.0] - 2026-08-23

### Changed - BREAKING

- **Dropped Python 3.9 support**; arequest now requires Python 3.10+.
- Raised the engine floor to `curl-cffi>=0.15.0`, which fixes an SSRF
  vulnerability in redirect handling (CVE-2026-33752 / GHSA-qw2m-4pqf-rmpp).

## [2.1.0] - 2026-08-23

### Added

- **WebSockets**: `Session.ws_connect(url)` opens impersonated WebSocket
  connections carrying the same TLS/HTTP fingerprint as HTTP requests; the
  returned handle supports `async with` and delegates to curl-impersonate's
  socket API (`send_json`, `recv_str`, `ping`, ...).
- **Bounded concurrent fetching**: `Session.iter_fetch(urls, max_concurrency=N)`
  yields responses as they complete with a hard cap on in-flight requests;
  optional `return_exceptions=True`.
- **Proxy pools**: new `arequest.ProxyPool` with `round_robin`, `random` and
  `failover` strategies, automatic failure cooldowns and recovery, and
  `pool.status()` introspection. Enable via `Session(proxy_pool=...)`;
  per-request `proxy=`/`proxies=` still take precedence.
- **Session persistence**: `await session.save(path)` and
  `await arequest.Session.load(path)` round-trip cookies, headers, timeouts,
  impersonation profile, proxies, retry policy, rate limits and connector
  limits through a versioned JSON file.
- **Type checking**: ships a PEP 561 `py.typed` marker - full IDE autocomplete.
- **CI/CD**: GitHub Actions workflow running lint + tests on Python 3.9-3.13
  (plus Windows), and trusted-publishing deployment to PyPI on `v*` tags.

## [2.0.0]

### Changed - BREAKING

- **New engine**: the pure-Python asyncio HTTP stack was replaced by a
  curl-impersonate powered transport (`curl-cffi`). Requests now present real
  browser fingerprints: byte-exact TLS ClientHello (JA3/JA4) and HTTP/2
  settings (Akamai), plus the full browser header set in correct order.
  Sessions impersonate Chrome by default; pass `impersonate=None` for plain
  requests.
- Removed the internal HTTP parser module (`arequest.parser`) and its
  `httptools` dependency; parsing is handled by libcurl.

### Migration from 1.x

```python
# 1.x (still works)
r = await arequest.get("https://example.com")

# New capabilities
async with arequest.Session(impersonate="chrome") as s:
    r = await s.get("https://example.com")
```

- The familiar API is unchanged: `Session`, `get/post/put/patch/delete/head/
  options`, `params/data/json/files/headers/timeout/verify/allow_redirects`,
  cookies, redirects, streaming (`aiter_content`/`aiter_lines`) and exceptions
  (`ClientError`, `ServerError`, `TimeoutError`, ...).
- Exceptions moved to a richer hierarchy rooted at `RequestError`; existing
  names still import from `arequest`.
- Requirements: Python 3.9+ and `curl-cffi>=0.13` (binary wheels available on
  all major platforms). `httptools` is no longer needed.
- New session options: `impersonate`, `ja3`, `akamai`, `extra_fp`,
  `http_version`, `retries`/`backoff`, `rate_limit*`, `proxy_pool`,
  `base_url`, `hooks`.

## [1.2.0] and earlier

- requests-compatible async client focused on throughput (connection pooling,
  keep-alive, DNS caching, multipart uploads, gzip support).
