# API Reference

All public names are importable from the top-level package:

```python
import arequest
```

## Constants

### `arequest.__version__`

Package version string.

## Core

### Session

Async HTTP session with connection pooling, cookies and browser impersonation.

```python
session = arequest.Session(
    headers=None,
    timeout=30.0,
    connector_limit=100,
    connector_limit_per_host=0,
    auth=None,
    verify=True,
    cookies=None,
    proxies=None,
    proxy=None,
    proxy_auth=None,
    base_url=None,
    params=None,
    trust_env=True,
    allow_redirects=True,
    max_redirects=30,
    impersonate="chrome",
    ja3=None,
    akamai=None,
    extra_fp=None,
    default_headers=True,
    default_encoding="utf-8",
    http_version="auto",        # auto | h1 | h2 | h3
    retries=0,                  # int or RetryPolicy
    backoff=None,
    stream=False,
    cert=None,
    interface=None,
    accept_encoding="gzip, deflate, br",
    rate_limit=None,            # requests/second
    rate_limit_per_host=None,
    rate_limit_burst=1,
    hooks=None,                 # {"request": fn, "response": fn}
)
```

Methods (all coroutines unless noted):

| Member | Description |
|---|---|
| `request(method, url, **kwargs)` | Generic request |
| `get(url, **kwargs)` / `post` / `put` / `patch` / `delete` / `head` / `options` | HTTP verbs |
| `bulk_get(urls, **kwargs)` | Concurrent GETs, returns list of `Response` |
| `gather(*specs, **kwargs)` | Concurrent mixed requests |
| `close()` | Close pools and connections |
| `headers` / `cookies` / `timeout` / `closed` / `transport_name` | Properties |

Common request kwargs: `headers`, `params`, `data`, `json`, `files`,
`cookies`, `timeout`, `verify`, `allow_redirects`, `max_redirects`, `auth`,
`proxies`/`proxy`/`proxy_auth`, `impersonate`, `ja3`, `akamai`, `extra_fp`,
`default_headers`, `http_version`, `stream`, `retries`, `backoff`, `referer`,
`hooks`.

### Response

Wraps the transport response with a requests-like interface.

Attributes:

```python
r.status_code      # int
r.ok               # bool - status < 400
r.reason           # str reason phrase
r.headers          # case-insensitive mapping
r.content          # bytes body
r.text             # decoded body
r.encoding         # detected or forced encoding
r.url              # final URL
r.elapsed          # seconds (float)
r.cookies          # response cookies
r.history          # redirect chain Responses
r.is_redirect      # bool
r.attempts         # attempts used including retries
r.http_version     # negotiated protocol version
r.request          # PreparedRequest actually sent
```

Methods:

| Method | Description |
|---|---|
| `json(**kwargs)` | Parse body as JSON |
| `decode(encoding=None)` | Decode body to text |
| `raise_for_status()` | Raise on 4xx/5xx |
| `iter_content(chunk_size)` | Sync chunk iterator over buffered body |
| `iter_lines()` | Sync line iterator over buffered body |
| `read()` | Await full streaming body |
| `aiter_content(chunk_size=None, decode_unicode=False)` | Async chunk stream |
| `aiter_lines(delimiter=b"\\n")` | Async line stream |
| `aclose()` / `close()` | Release body and connection |

Usable as an async context manager.

### PreparedRequest

Dataclass describing the outgoing request: `method`, `url`, `headers`,
`attempt`. Delivered to request hooks and attached to errors/responses.

### Timeout

Structured timeout: `Timeout(total=30.0, connect=None, read=None)`. Plain
numbers and `(connect, read)` tuples are accepted anywhere a timeout is
expected.

## Impersonation

### `available_profiles(include_aliases=False) -> tuple[str, ...]`

Valid `impersonate` profile names for the installed engine
(e.g. `"chrome"`, `"chrome131"`, `"safari184"`, `"firefox135"`).

Per-request/session fingerprint overrides: `ja3` (raw JA3 string), `akamai`
(raw HTTP/2 fingerprint string), `extra_fp` (dict of extra fingerprint tweaks).

## Authentication

See [auth.md](auth.md) for details.

- `BasicAuth(username, password)`
- `BearerAuth(token)`
- `AuthBase` - base class for custom handlers (`apply(request)`)

## Retry Policy

### `RetryPolicy`

Frozen dataclass controlling automatic retries:

```python
RetryPolicy(
    total=0,                     # max retries per request
    backoff_factor=0.25,
    max_backoff=30.0,
    jitter=0.1,
    status_forcelist=frozenset((429, 500, 502, 503, 504)),
    allowed_methods=frozenset(("DELETE", "GET", "HEAD", "OPTIONS", "PUT")),
    respect_retry_after_header=True,
)
```

Pass either an `int` retry count or a `RetryPolicy` via `retries=`; tune the
base delay with `backoff=`.

## Exceptions

All exceptions derive from `RequestError`.

```
RequestError
├── TransportError
│   ├── ConnectionError
│   │   └── ProxyError
│   ├── TimeoutError
│   └── SSLError
├── HTTPError            # .status_code
│   ├── ClientError      # 4xx
│   └── ServerError      # 5xx
├── InvalidURL
├── TooManyRedirects
├── ImpersonationError
└── StreamError
```

Connection and timeout errors carry `retryable=True` for the retry engine.

## Top-Level Helpers

Implicit per-event-loop session (created lazily):

```python
await arequest.get(url, **kwargs)
await arequest.post(url, **kwargs)
# ... put, patch, delete, head, options
await arequest.request("GET", url, **kwargs)
await arequest.aclose()   # close the implicit session
```
