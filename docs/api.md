# API Reference

## Overview

This document provides a comprehensive reference for the arequest public API. arequest exposes its functionality through the main `arequest` module, which can be imported as:

```python
import arequest
```

All public classes, functions, and exceptions are available directly from the `arequest` namespace.

---

## Version

### `__version__`

Current version of arequest.

```python
import arequest
print(arequest.__version__)  # '0.2.0'
```

**Type:** `str`

---

## Core Classes

### Session

High-performance HTTP session with connection pooling and persistent configuration.

**Import:** `from arequest import Session`

**See:** [`client.md`](client.md#session) for detailed documentation

**Constructor Signature:**

```python
Session(
    headers: Optional[dict[str, str]] = None,
    timeout: Optional[float] = None,
    connector_limit: int = 100,
    connector_limit_per_host: int = 30,
    auth: Optional[AuthBase] = None,
    verify: bool = True
) -> Session
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| [`request()`](client.md#requestmethod-url-kwargs) | `async request(method: str, url: str, **kwargs) -> Response` | Make an HTTP request |
| [`get()`](client.md#geturl-kwargs) | `async get(url: str, **kwargs) -> Response` | Make a GET request |
| [`post()`](client.md#posturl-kwargs) | `async post(url: str, **kwargs) -> Response` | Make a POST request |
| [`put()`](client.md#puturl-kwargs) | `async put(url: str, **kwargs) -> Response` | Make a PUT request |
| [`delete()`](client.md#deleteurl-kwargs) | `async delete(url: str, **kwargs) -> Response` | Make a DELETE request |
| [`patch()`](client.md#patchurl-kwargs) | `async patch(url: str, **kwargs) -> Response` | Make a PATCH request |
| [`head()`](client.md#headurl-kwargs) | `async head(url: str, **kwargs) -> Response` | Make a HEAD request |
| [`options()`](client.md#optionsurl-kwargs) | `async options(url: str, **kwargs) -> Response` | Make an OPTIONS request |
| [`gather()`](client.md#gatherrequests-kwargs) | `async gather(*requests, **kwargs) -> list[Response]` | Execute multiple requests concurrently |
| [`bulk_get()`](client.md#bulk_geturls-kwargs) | `async bulk_get(urls: list[str], **kwargs) -> list[Response]` | Execute multiple GET requests concurrently |
| [`close()`](client.md#close) | `async close() -> None` | Close the session and all connections |

**Context Manager Support:**

```python
async with Session() as session:
    response = await session.get('https://example.com')
```

**Example:**

```python
import arequest

async def main():
    async with arequest.Session() as session:
        response = await session.get('https://api.example.com/data')
        print(response.json())

asyncio.run(main())
```

---

### Response

HTTP response object with lazy decoding, similar to `requests.Response`.

**Import:** `from arequest import Response`

**See:** [`client.md`](client.md#response) for detailed documentation

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| [`status_code`](client.md#properties) | `int` | HTTP status code |
| [`headers`](client.md#properties) | `dict[str, str]` | Response headers |
| [`url`](client.md#properties) | `str` | Requested URL |
| [`content`](client.md#properties) | `bytes` | Raw response body |
| [`text`](client.md#properties) | `str` | Decoded response body |
| [`encoding`](client.md#properties) | `str` | Character encoding |
| [`reason`](client.md#properties) | `str` | HTTP reason phrase |
| [`elapsed`](client.md#properties) | `float` | Request duration in seconds |
| [`ok`](client.md#properties) | `bool` | `True` if status code < 400 |

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| [`json()`](client.md#json) | `json() -> Any` | Parse response body as JSON |
| [`decode()`](client.md#decodeencoding-none) | `decode(encoding: Optional[str] = None) -> str` | Decode response body with optional encoding |
| [`raise_for_status()`](client.md#raise_for_status) | `raise_for_status() -> None` | Raise exception for 4xx/5xx status codes |

**Example:**

```python
response = await session.get('https://api.example.com/data')

# Access properties
print(response.status_code)  # 200
print(response.headers['Content-Type'])  # application/json
print(response.text)  # Response body as string
print(response.content)  # Response body as bytes

# Parse JSON
data = response.json()

# Check status
if response.ok:
    print("Success!")
else:
    response.raise_for_status()
```

---

## Authentication Classes

### AuthBase

Abstract base class for authentication handlers.

**Import:** `from arequest import AuthBase`

**See:** [`auth.md`](auth.md#authbase) for detailed documentation

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| [`apply()`](auth.md#applyrequest) | `apply(request: Any) -> None` | Apply authentication to request |

**Example:**

```python
from arequest import AuthBase

class CustomAuth(AuthBase):
    def __init__(self, token: str):
        self.token = token
    
    def apply(self, request):
        request.headers['X-Custom-Auth'] = self.token
```

---

### BasicAuth

HTTP Basic Authentication implementation.

**Import:** `from arequest import BasicAuth`

**See:** [`auth.md`](auth.md#basicauth) for detailed documentation

**Constructor Signature:**

```python
BasicAuth(username: str, password: str) -> BasicAuth
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | `str` | Username for authentication |
| `password` | `str` | Password for authentication |

**Example:**

```python
import arequest

auth = arequest.BasicAuth('myuser', 'mypassword')

async with arequest.Session(auth=auth) as session:
    response = await session.get('https://api.example.com/protected')
```

---

### BearerAuth

Bearer Token Authentication implementation.

**Import:** `from arequest import BearerAuth`

**See:** [`auth.md`](auth.md#bearerauth) for detailed documentation

**Constructor Signature:**

```python
BearerAuth(token: str) -> BearerAuth
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | `str` | Bearer token string |

**Example:**

```python
import arequest

auth = arequest.BearerAuth('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...')

async with arequest.Session(auth=auth) as session:
    response = await session.get('https://api.example.com/protected')
```

---

## Convenience Functions

### request

Make an HTTP request with a temporary session.

**Import:** `from arequest import request`

**Signature:**

```python
async request(method: str, url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `method` | `str` | HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS) |
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters (same as [`Session.request()`](client.md#requestmethod-url-kwargs)) |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.request('GET', 'https://api.example.com/data')
print(response.json())
```

---

### get

Make a GET request with a temporary session.

**Import:** `from arequest import get`

**Signature:**

```python
async get(url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.get('https://api.example.com/data')
print(response.json())
```

---

### post

Make a POST request with a temporary session.

**Import:** `from arequest import post`

**Signature:**

```python
async post(url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters (including `json`, `data`) |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.post(
    'https://api.example.com/users',
    json={'name': 'Alice', 'email': 'alice@example.com'}
)
print(response.json())
```

---

### put

Make a PUT request with a temporary session.

**Import:** `from arequest import put`

**Signature:**

```python
async put(url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters (including `json`, `data`) |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.put(
    'https://api.example.com/users/1',
    json={'name': 'Updated Name'}
)
print(response.json())
```

---

### delete

Make a DELETE request with a temporary session.

**Import:** `from arequest import delete`

**Signature:**

```python
async delete(url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.delete('https://api.example.com/users/1')
print(f"Status: {response.status_code}")
```

---

### patch

Make a PATCH request with a temporary session.

**Import:** `from arequest import patch`

**Signature:**

```python
async patch(url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters (including `json`, `data`) |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.patch(
    'https://api.example.com/users/1',
    json={'email': 'newemail@example.com'}
)
print(response.json())
```

---

### head

Make a HEAD request with a temporary session.

**Import:** `from arequest import head`

**Signature:**

```python
async head(url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.head('https://api.example.com/data')
print(response.headers)
```

---

### options

Make an OPTIONS request with a temporary session.

**Import:** `from arequest import options`

**Signature:**

```python
async options(url: str, **kwargs) -> Response
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Target URL |
| `**kwargs` | `dict` | Additional request parameters |

**Returns:** `Response`

**Example:**

```python
import arequest

response = await arequest.options('https://api.example.com/data')
print(response.headers.get('Allow'))
```

---

## Exceptions

### ClientError

Exception raised for 4xx client errors.

**Import:** `from arequest import ClientError`

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `status_code` | `int` | HTTP status code (400-499) |

**Example:**

```python
import arequest

try:
    response = await arequest.get('https://api.example.com/notfound')
    response.raise_for_status()
except arequest.ClientError as e:
    print(f"Client error: {e.status_code}")
    # Output: Client error: 404
```

---

### ServerError

Exception raised for 5xx server errors.

**Import:** `from arequest import ServerError`

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `status_code` | `int` | HTTP status code (500-599) |

**Example:**

```python
import arequest

try:
    response = await arequest.get('https://api.example.com/error')
    response.raise_for_status()
except arequest.ServerError as e:
    print(f"Server error: {e.status_code}")
    # Output: Server error: 500
```

---

### TimeoutError

Exception raised when a request times out.

**Import:** `from arequest import TimeoutError`

**Example:**

```python
import arequest

try:
    response = await arequest.get('https://api.example.com/slow', timeout=1.0)
except arequest.TimeoutError:
    print("Request timed out")
```

---

## Request Parameters

### Common Parameters

These parameters are accepted by all request methods:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `headers` | `dict[str, str]` | `None` | Request headers |
| `params` | `dict[str, Any]` | `None` | Query parameters |
| `data` | `Union[bytes, str, dict]` | `None` | Form data or raw body |
| `json` | `Any` | `None` | JSON body (auto-serialized) |
| `timeout` | `float` | `None` | Request timeout in seconds |
| `verify` | `bool` | `None` | SSL verification |
| `allow_redirects` | `bool` | `True` | Follow HTTP redirects |
| `max_redirects` | `int` | `10` | Maximum redirect count |
| `auth` | `AuthBase` | `None` | Authentication |

### Parameter Details

#### headers

Dictionary of HTTP headers to send with the request.

```python
response = await session.get(
    'https://api.example.com/data',
    headers={
        'User-Agent': 'MyApp/1.0',
        'Accept': 'application/json',
        'X-Custom-Header': 'value'
    }
)
```

#### params

Dictionary of query parameters to append to the URL.

```python
response = await session.get(
    'https://api.example.com/search',
    params={
        'q': 'python',
        'page': 2,
        'limit': 10
    }
)
# URL becomes: https://api.example.com/search?q=python&page=2&limit=10
```

#### data

Form data or raw request body.

**As dictionary (form-encoded):**

```python
response = await session.post(
    'https://api.example.com/login',
    data={
        'username': 'user',
        'password': 'pass'
    }
)
```

**As string:**

```python
response = await session.post(
    'https://api.example.com/data',
    data='raw body content'
)
```

**As bytes:**

```python
response = await session.post(
    'https://api.example.com/upload',
    data=b'binary data'
)
```

#### json

JSON body that will be automatically serialized.

```python
response = await session.post(
    'https://api.example.com/users',
    json={
        'name': 'Alice',
        'email': 'alice@example.com',
        'age': 30
    }
)
# Automatically sets Content-Type: application/json
```

#### timeout

Request timeout in seconds.

```python
# Request-level timeout
response = await session.get(
    'https://api.example.com/data',
    timeout=10.0
)

# Session-level timeout
async with arequest.Session(timeout=30.0) as session:
    response = await session.get('https://api.example.com/data')
```

#### verify

SSL certificate verification.

```python
# Disable SSL verification (not recommended for production)
response = await session.get(
    'https://self-signed.example.com/data',
    verify=False
)

# Session-level verification
async with arequest.Session(verify=False) as session:
    response = await session.get('https://api.example.com/data')
```

#### allow_redirects

Whether to follow HTTP redirects.

```python
# Disable redirects
response = await session.get(
    'https://api.example.com/redirect',
    allow_redirects=False
)

# Custom redirect limit
response = await session.get(
    'https://api.example.com/redirect',
    max_redirects=5
)
```

#### auth

Authentication for the request.

```python
import arequest

# Request-level auth
response = await session.get(
    'https://api.example.com/protected',
    auth=arequest.BasicAuth('user', 'pass')
)

# Session-level auth
async with arequest.Session(auth=arequest.BearerAuth('token')) as session:
    response = await session.get('https://api.example.com/protected')
```

---

## Complete API Examples

### Basic Usage

```python
import asyncio
import arequest

async def main():
    # Simple GET request
    response = await arequest.get('https://httpbin.org/get')
    print(response.json())

asyncio.run(main())
```

### Session with Multiple Requests

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Multiple requests with connection reuse
        responses = await session.bulk_get([
            'https://httpbin.org/get?i=1',
            'https://httpbin.org/get?i=2',
            'https://httpbin.org/get?i=3'
        ])
        
        for response in responses:
            print(f"{response.url}: {response.status_code}")

asyncio.run(main())
```

### POST with JSON

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        response = await session.post(
            'https://httpbin.org/post',
            json={'key': 'value', 'number': 42}
        )
        print(response.json())

asyncio.run(main())
```

### Authentication

```python
import asyncio
import arequest

async def main():
    # Basic Authentication
    auth1 = arequest.BasicAuth('username', 'password')
    
    # Bearer Authentication
    auth2 = arequest.BearerAuth('your-token-here')
    
    async with arequest.Session(auth=auth1) as session:
        response = await session.get('https://httpbin.org/basic-auth/username/password')
        print(f"Status: {response.status_code}")

asyncio.run(main())
```

### Error Handling

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        try:
            response = await session.get('https://httpbin.org/status/404')
            response.raise_for_status()
        except arequest.ClientError as e:
            print(f"Client error: {e.status_code}")
        except arequest.ServerError as e:
            print(f"Server error: {e.status_code}")
        except arequest.TimeoutError:
            print("Request timed out")

asyncio.run(main())
```

### Concurrent Requests

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Mixed methods
        responses = await session.gather(
            ('GET', 'https://httpbin.org/get'),
            ('POST', 'https://httpbin.org/post'),
            'https://httpbin.org/uuid'  # Defaults to GET
        )
        
        for response in responses:
            print(f"{response.url}: {response.status_code}")

asyncio.run(main())
```

For per-request payloads, build tasks manually:

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        tasks = [
            session.request('POST', 'https://httpbin.org/post', json={'key': 'value'}),
            session.request('GET', 'https://httpbin.org/uuid'),
        ]
        responses = await asyncio.gather(*tasks)
        for response in responses:
            print(f"{response.url}: {response.status_code}")

asyncio.run(main())
```

### Custom Headers and Parameters

```python
import asyncio
import arequest

async def main():
    async with arequest.Session(
        headers={'User-Agent': 'MyApp/1.0'},
        timeout=30.0
    ) as session:
        response = await session.get(
            'https://httpbin.org/get',
            params={'key1': 'value1', 'key2': 'value2'},
            headers={'X-Custom-Header': 'custom-value'}
        )
        print(response.json())

asyncio.run(main())
```

---

## Type Hints

arequest provides full type hints for better IDE support and type checking.

```python
from arequest import Session, Response, BasicAuth
from typing import Optional, Dict, Any

async def fetch_data(
    session: Session,
    url: str,
    params: Optional[Dict[str, Any]] = None
) -> Response:
    """Fetch data from API with type hints."""
    response = await session.get(url, params=params)
    response.raise_for_status()
    return response
```

---

## See Also

- [`client.md`](client.md) - Detailed client and session documentation
- [`auth.md`](auth.md) - Authentication handlers documentation
- [`parser.md`](parser.md) - HTTP parsing implementation details
- [`README.md`](../README.md) - Project overview and quick start guide
