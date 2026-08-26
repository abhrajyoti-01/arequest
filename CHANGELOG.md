# Changelog

All notable changes to `arequest` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.3.0] - 2026-08-26

### Security

- Masked `user:password` userinfo in all URLs embedded in exception messages
  (`translate_exception`, `TooManyRedirects`, `InvalidURL`) so credentials no
  longer leak into logs.
- `Session.save()` now creates the state file with owner-only permissions
  (`0600`) since it contains cookies and proxy credentials.
- Redirect targets are validated for out-of-range ports (previously raised an
  unhandled `ValueError`) and control characters before being followed.
- Request, WebSocket and redirect URLs reject control characters up front with
  a clear `InvalidURL`.
- `ProxyPool.status()` masks proxy credentials in its output.

### Changed

- **Speed: hot-path fast path.** When neither rate limiting nor connection
  limits are configured, `Session.request` now skips the per-request origin
  parse and semaphore/limiter acquisition entirely (a `_needs_limiting` flag
  computed once at construction). Measured ~20% fewer Python-side CPU cycles
  per request on the pure hot path when limits are disabled.
- **Speed: lazy `Response.history`.** Redirect history is now built on first
  access instead of eagerly constructing child `Response` objects for every
  response; the common no-redirect case performs no recursion.
- **Speed: cached curl error classes.** Exception translation reuses the
  curl-cffi exceptions module imported once at load time, instead of a
  per-call import.
- **Speed: redirect fast path.** Same-origin redirects that keep the HTTP
  method no longer rebuild the headers object or scrub the options mapping.
- **Smoothness: rewritten `AsyncRateLimiter`.** Replaced the busy
  sleep-and-retry poll loop with a token bucket using a FIFO waiter schedule,
  eliminating thundering-herd wakeups and giving even pacing under contention.
- **Smoothness: `iter_fetch` worker pool.** Rewritten from the O(n^2)
  `asyncio.wait(FIRST_COMPLETED)` pattern to a fixed worker pool feeding an
  `asyncio.Queue`, with graceful shutdown (no blanket `task.cancel()` of the
  whole batch) and clean teardown when an error aborts iteration.

### Added

- **`rate_limit_jitter`**: optional extra random delay added to rate-limit
  pacing to smooth bursts (default `0.0`).
- **`realistic_headers`**: when `True`, layer a coherent browser header set
  (`Accept-Language`, `Sec-Fetch-*`, `Sec-CH-UA`, `Upgrade-Insecure-Requests`,
  matching the impersonate profile) onto each request without overriding
  headers the caller explicitly set (default `False`).
- **`user_agent_rotation`**: rotate the User-Agent header per request. Pass
  `"auto"` to derive a pool from the `impersonate` profile, a single UA
  string, or an iterable of UA strings (default `None` = no rotation).
- **`think_time`**: human-like pacing between requests - a number of seconds
  or a `(min, max)` tuple for a randomized inter-request delay (default
  `None`).
- All realistic-header options default off to preserve backwards
  compatibility, and are persisted by `Session.save()`/`Session.load()`.

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
