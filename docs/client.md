# Client Guide

## Session

`arequest.Session` manages connection pools, cookies, headers, auth, retries
and impersonation settings across many requests.

```python
import arequest

session = arequest.Session(
    headers={"User-Agent": "my-app"},   # merged over browser defaults
    timeout=30.0,
    connector_limit=100,                # global concurrent connections
    connector_limit_per_host=0,         # 0 = unlimited per host
    verify=True,
    impersonate="chrome",
    http_version="auto",                # auto | h1 | h2 | h3
    retries=0,
)
```

Use it as an async context manager so connections are closed deterministically:

```python
async with arequest.Session() as session:
    r = await session.get("https://httpbin.org/get")
```

or close it manually with `await session.close()`.

## Making Requests

All methods return a `Response`: `get`, `post`, `put`, `patch`, `delete`,
`head`, `options`, plus the generic `session.request(method, url, ...)`.

```python
await session.get(url, params={"page": 1})
await session.post(url, json={"key": "value"})
await session.post(url, data={"form": "field"})
await session.post(url, files={"f": ("a.txt", b"content")})
```

Every session option can be overridden per request:

```python
await session.get(url, timeout=(3.0, 10.0), verify=False,
                  allow_redirects=False, impersonate="safari184")
```

### Concurrency helpers

```python
# Many GETs at once
responses = await session.bulk_get(urls)

# Mixed methods: ("METHOD", url) or ("METHOD", url, {kwargs}) or {"method": ..., "url": ..., ...}
responses = await session.gather(
    ("GET", "https://httpbin.org/get"),
    ("POST", "https://httpbin.org/post", {"json": {"x": 1}}),
)

# Or plain asyncio.gather
responses = await asyncio.gather(*(session.get(u) for u in urls))
```

### Base URL and default params

```python
session = arequest.Session(base_url="https://api.example.com/v1", params={"key": "..."})
r = await session.get("/users/42")   # -> https://api.example.com/v1/users/42?key=...
```

### Hooks

```python
def add_header(request):
    request.headers["X-Trace"] = "..."
    return request

session = arequest.Session(hooks={"request": add_header})
```

Hooks may be async; `response` hooks receive the `Response` and must return it
(or another `Response`) or `None`.

## Impersonation

```python
session = arequest.Session(impersonate="chrome")     # latest Chrome profile
await session.get(url, impersonate="chrome131")      # per-request override
arequest.available_profiles()                        # tuple of valid names
```

Raw fingerprint overrides are also supported for advanced use:

```python
await session.get(url, ja3="771,4865-...", akamai="1:65536;...", extra_fp={...})
```

Set `default_headers=False` to send only your explicit headers (no injected
browser header set).

## Response

```python
r.status_code        # int HTTP status
r.ok                 # True if status < 400
r.reason             # reason phrase
r.headers            # case-insensitive mapping
r.content            # bytes body
r.text               # decoded body
r.json()             # parsed JSON (uses orjson when available)
r.encoding           # text encoding; assign to override decoding
r.url                # final URL after redirects
r.elapsed            # total seconds
r.cookies            # cookies received with this response
r.history            # list of redirect Responses
r.redirect_count     # number of redirects followed
r.is_redirect        # True on 3xx with a Location header
r.attempts           # attempts used, including retries
r.http_version       # negotiated version (e.g. 2 for h2)
r.raise_for_status() # raise ClientError / ServerError on 4xx / 5xx
```

## Streaming

Request with `stream=True` (per request or on the session), then iterate:

```python
async with arequest.Session(stream=True) as session:
    r = await session.get(large_url)
    async for chunk in r.aiter_content(chunk_size=64 * 1024):
        handle(chunk)

    r2 = await session.get(log_url)
    async for line in r2.aiter_lines():
        print(line)
```

Always consume or close streaming responses (`await r.aclose()`, or use the
`async with` form) so the connection returns to the pool.

## Cookies

Cookies persist across requests like `requests.Session`:

```python
async with arequest.Session() as session:
    await session.get("https://httpbin.org/cookies/set/a/1")
    print(dict(session.cookies))
```

Seed the jar with `Session(cookies={"a": "1"})`; replace it any time via
`session.cookies = {...}`.

## Timeouts

```python
await session.get(url, timeout=5.0)          # whole request
await session.get(url, timeout=(3.0, 10.0))  # connect, read
```

## Redirects

Redirects follow browser semantics by default (303/301/302 POST become GET,
auth/cookie headers drop on cross-origin hops).

```python
r = await session.get(url, allow_redirects=False)
r = await session.get(url, max_redirects=5)
r.history        # intermediate responses
```
