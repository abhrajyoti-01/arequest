# Client Module Documentation

## Overview

The [`client.py`](../src/arequest/client.py) module provides the core HTTP client functionality for arequest, including:

- High-performance async HTTP client with connection pooling
- [`Session`](../src/arequest/client.py:355) class for connection reuse and persistent configuration
- [`Response`](../src/arequest/client.py:44) class for handling HTTP responses
- Convenience functions for one-off requests
- Connection pooling with keep-alive support
- DNS caching for improved performance
- SSL/TLS support with verification options

---

## Classes

### Response

The [`Response`](../src/arequest/client.py:44) class represents an HTTP response with lazy decoding, similar to `requests.Response`.

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| [`status_code`](../src/arequest/client.py:61) | `int` | HTTP status code (e.g., 200, 404) |
| [`headers`](../src/arequest/client.py:62) | `dict[str, str]` | Response headers |
| [`url`](../src/arequest/client.py:63) | `str` | The URL that was requested |
| [`content`](../src/arequest/client.py:74) | `bytes` | Raw response body |
| [`text`](../src/arequest/client.py:79) | `str` | Response body decoded as text |
| [`encoding`](../src/arequest/client.py:71) | `str` | Character encoding (detected from Content-Type) |
| [`reason`](../src/arequest/client.py:67) | `str` | HTTP reason phrase (e.g., "OK", "Not Found") |
| [`elapsed`](../src/arequest/client.py:68) | `float` | Request duration in seconds |
| [`ok`](../src/arequest/client.py:70) | `bool` | `True` if status code < 400 |

#### Methods

##### [`json()`](../src/arequest/client.py:91)

Parse response body as JSON.

```python
response = await session.get('https://api.example.com/data')
data = response.json()  # Returns parsed JSON object
```

**Returns:** `Any` - Parsed JSON data (dict, list, etc.)

**Raises:** `json.JSONDecodeError` if response body is not valid JSON

##### [`decode(encoding=None)`](../src/arequest/client.py:85)

Decode response body with optional encoding override.

```python
# Use detected encoding
text = response.decode()

# Override encoding
text = response.decode('iso-8859-1')
```

**Parameters:**
- `encoding` (`Optional[str]`): Character encoding to use. If `None`, uses detected encoding.

**Returns:** `str` - Decoded response body

##### [`raise_for_status()`](../src/arequest/client.py:105)

Raise an exception for 4xx/5xx status codes.

```python
response = await session.get('https://api.example.com/data')
response.raise_for_status()  # Raises ClientError or ServerError if status >= 400
```

**Raises:**
- [`ClientError`](../src/arequest/client.py:122) - For 4xx status codes
- [`ServerError`](../src/arequest/client.py:129) - For 5xx status codes

---

### Session

The [`Session`](../src/arequest/client.py:355) class provides a high-performance HTTP session with connection pooling. It's recommended for making multiple requests as it reuses connections.

#### Constructor

```python
Session(
    headers: Optional[dict[str, str]] = None,
    timeout: Optional[float] = None,
    connector_limit: int = 100,
    connector_limit_per_host: int = 30,
    auth: Optional[AuthBase] = None,
    verify: bool = True
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `headers` | `dict[str, str]` | `None` | Default headers for all requests |
| `timeout` | `float` | `None` | Default timeout in seconds for all requests |
| `connector_limit` | `int` | `100` | Total connection limit across all hosts |
| `connector_limit_per_host` | `int` | `30` | Maximum connections per host |
| `auth` | `AuthBase` | `None` | Default authentication for all requests |
| `verify` | `bool` | `True` | SSL certificate verification |

**Example:**

```python
import arequest

# Create session with custom configuration
session = arequest.Session(
    headers={"User-Agent": "MyApp/1.0"},
    timeout=30.0,
    connector_limit=50,
    verify=True
)

async with session:
    response = await session.get('https://api.example.com/data')
```

#### Methods

##### [`request(method, url, **kwargs)`](../src/arequest/client.py:434)

Make an HTTP request with full control over parameters.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `method` | `str` | Required | HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS) |
| `url` | `str` | Required | Target URL |
| `headers` | `dict[str, str]` | `None` | Request headers (merged with session defaults) |
| `params` | `dict[str, Any]` | `None` | Query parameters to append to URL |
| `data` | `Union[bytes, str, dict]` | `None` | Form data or raw request body |
| `json` | `Any` | `None` | JSON body (automatically serialized) |
| `timeout` | `float` | `None` | Request timeout in seconds |
| `verify` | `bool` | `None` | SSL verification (overrides session default) |
| `allow_redirects` | `bool` | `True` | Follow HTTP redirects |
| `max_redirects` | `int` | `10` | Maximum number of redirects to follow |
| `auth` | `AuthBase` | `None` | Authentication for this request |

**Returns:** [`Response`](../src/arequest/client.py:44) - HTTP response object

**Example:**

```python
# POST with JSON body
response = await session.request(
    'POST',
    'https://api.example.com/users',
    json={'name': 'Alice', 'email': 'alice@example.com'},
    headers={'X-Custom-Header': 'value'}
)

# PUT with form data
response = await session.request(
    'PUT',
    'https://api.example.com/users/1',
    data={'name': 'Bob', 'email': 'bob@example.com'}
)

# GET with query parameters
response = await session.request(
    'GET',
    'https://api.example.com/search',
    params={'q': 'python', 'limit': 10}
)
```

##### [`get(url, **kwargs)`](../src/arequest/client.py:581)

Make a GET request.

```python
response = await session.get('https://api.example.com/data')
response = await session.get('https://api.example.com/data', timeout=10.0)
```

##### [`post(url, **kwargs)`](../src/arequest/client.py:585)

Make a POST request.

```python
# POST with JSON
response = await session.post(
    'https://api.example.com/users',
    json={'name': 'Alice'}
)

# POST with form data
response = await session.post(
    'https://api.example.com/login',
    data={'username': 'user', 'password': 'pass'}
)
```

##### [`put(url, **kwargs)`](../src/arequest/client.py:589)

Make a PUT request.

```python
response = await session.put(
    'https://api.example.com/users/1',
    json={'name': 'Updated Name'}
)
```

##### [`delete(url, **kwargs)`](../src/arequest/client.py:593)

Make a DELETE request.

```python
response = await session.delete('https://api.example.com/users/1')
```

##### [`patch(url, **kwargs)`](../src/arequest/client.py:597)

Make a PATCH request.

```python
response = await session.patch(
    'https://api.example.com/users/1',
    json={'email': 'newemail@example.com'}
)
```

##### [`head(url, **kwargs)`](../src/arequest/client.py:601)

Make a HEAD request (returns headers only).

```python
response = await session.head('https://api.example.com/data')
print(response.headers)
```

##### [`options(url, **kwargs)`](../src/arequest/client.py:605)

Make an OPTIONS request.

```python
response = await session.options('https://api.example.com/data')
print(response.headers.get('Allow'))
```

##### [`gather(*requests, **kwargs)`](../src/arequest/client.py:609)

Execute multiple requests concurrently. This is the recommended way to make multiple requests for maximum performance.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `*requests` | `tuple[str, str]` or `str` | Request tuples `(method, url)` or URLs (defaults to GET) |
| `**kwargs` | `dict` | Common arguments applied to all requests |

**Returns:** `list[Response]` - List of response objects in the same order as requests

**Example:**

```python
# Mixed methods
responses = await session.gather(
    ('GET', 'https://api.example.com/users'),
    ('POST', 'https://api.example.com/data'),
    'https://api.example.com/config'  # Defaults to GET
)

# All GET requests with common timeout
responses = await session.gather(
    'https://api.example.com/data1',
    'https://api.example.com/data2',
    'https://api.example.com/data3',
    timeout=10.0
)
```

##### [`bulk_get(urls, **kwargs)`](../src/arequest/client.py:644)

Execute multiple GET requests concurrently. This is the most efficient way to fetch multiple URLs.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `urls` | `list[str]` | List of URLs to fetch |
| `**kwargs` | `dict` | Common arguments applied to all requests |

**Returns:** `list[Response]` - List of response objects in the same order as URLs

**Example:**

```python
# Fetch 100 URLs concurrently
urls = [f'https://api.example.com/items/{i}' for i in range(100)]
responses = await session.bulk_get(urls, timeout=5.0)

# Process responses
for i, response in enumerate(responses):
    print(f"Item {i}: {response.status_code}")
```

##### [`close()`](../src/arequest/client.py:663)

Close the session and all connections.

```python
session = arequest.Session()
try:
    response = await session.get('https://api.example.com/data')
finally:
    await session.close()
```

**Note:** When using `async with` context manager, this is called automatically.

#### Context Manager

The [`Session`](../src/arequest/client.py:355) class supports async context manager protocol:

```python
async with arequest.Session() as session:
    response = await session.get('https://api.example.com/data')
# Session automatically closed here
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `auth` | `Optional[AuthBase]` | Default authentication for requests |
| `cookies` | `dict[str, str]` | Session cookies (currently for storage only) |
| `verify` | `bool` | SSL verification setting |

---

### _ConnectionPool

**Internal class** - High-performance connection pool for a single host.

The [`_ConnectionPool`](../src/arequest/client.py:141) class manages connections to a specific host with:

- DNS caching (60-second TTL)
- Connection reuse with keep-alive
- Configurable pool size and idle timeout
- TCP_NODELAY optimization

**Note:** This is an internal implementation detail. Users interact with it indirectly through the [`Session`](../src/arequest/client.py:355) class.

---

## Exceptions

### ClientError

Exception raised for 4xx client errors.

```python
try:
    response = await session.get('https://api.example.com/notfound')
    response.raise_for_status()
except arequest.ClientError as e:
    print(f"Client error: {e.status_code}")
```

**Attributes:**
- `status_code` (`int`): The HTTP status code

### ServerError

Exception raised for 5xx server errors.

```python
try:
    response = await session.get('https://api.example.com/error')
    response.raise_for_status()
except arequest.ServerError as e:
    print(f"Server error: {e.status_code}")
```

**Attributes:**
- `status_code` (`int`): The HTTP status code

### TimeoutError

Exception raised when a request times out.

```python
try:
    response = await session.get('https://api.example.com/slow', timeout=1.0)
except arequest.TimeoutError:
    print("Request timed out")
```

---

## Convenience Functions

The module provides convenience functions for simple one-off requests without managing a session explicitly. These functions create a temporary session, make the request, and close the session.

### [`request(method, url, **kwargs)`](../src/arequest/client.py:681)

Make an HTTP request with a temporary session.

```python
response = await arequest.request('GET', 'https://api.example.com/data')
```

### [`get(url, **kwargs)`](../src/arequest/client.py:687)

Make a GET request with a temporary session.

```python
response = await arequest.get('https://api.example.com/data')
```

### [`post(url, **kwargs)`](../src/arequest/client.py:693)

Make a POST request with a temporary session.

```python
response = await arequest.post(
    'https://api.example.com/users',
    json={'name': 'Alice'}
)
```

### [`put(url, **kwargs)`](../src/arequest/client.py:699)

Make a PUT request with a temporary session.

```python
response = await arequest.put(
    'https://api.example.com/users/1',
    json={'name': 'Bob'}
)
```

### [`delete(url, **kwargs)`](../src/arequest/client.py:705)

Make a DELETE request with a temporary session.

```python
response = await arequest.delete('https://api.example.com/users/1')
```

### [`patch(url, **kwargs)`](../src/arequest/client.py:711)

Make a PATCH request with a temporary session.

```python
response = await arequest.patch(
    'https://api.example.com/users/1',
    json={'email': 'new@example.com'}
)
```

### [`head(url, **kwargs)`](../src/arequest/client.py:717)

Make a HEAD request with a temporary session.

```python
response = await arequest.head('https://api.example.com/data')
```

### [`options(url, **kwargs)`](../src/arequest/client.py:723)

Make an OPTIONS request with a temporary session.

```python
response = await arequest.options('https://api.example.com/data')
```

---

## Usage Examples

### Basic Request

```python
import asyncio
import arequest

async def main():
    response = await arequest.get('https://httpbin.org/get')
    print(response.status_code)
    print(response.json())

asyncio.run(main())
```

### Session with Connection Reuse

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Reuse connection for multiple requests
        for i in range(10):
            response = await session.get(f'https://httpbin.org/get?i={i}')
            print(f"Request {i}: {response.status_code}")

asyncio.run(main())
```

### Concurrent Requests with bulk_get

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        urls = [f'https://httpbin.org/get?i={i}' for i in range(100)]
        responses = await session.bulk_get(urls)
        
        for response in responses:
            print(f"{response.url}: {response.status_code}")

asyncio.run(main())
```

### Mixed Methods with gather

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        responses = await session.gather(
            ('GET', 'https://httpbin.org/get'),
            ('POST', 'https://httpbin.org/post'),
            ('PUT', 'https://httpbin.org/put'),
            'https://httpbin.org/uuid'  # Defaults to GET
        )
        
        for response in responses:
            print(f"{response.url}: {response.status_code}")

asyncio.run(main())
```

For per-request payloads, build tasks yourself:

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        tasks = [
            session.request('POST', 'https://httpbin.org/post', json={'key': 'value'}),
            session.request('PUT', 'https://httpbin.org/put', data={'key': 'value'}),
        ]
        responses = await asyncio.gather(*tasks)
        for response in responses:
            print(f"{response.url}: {response.status_code}")

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

### Custom Headers and Authentication

```python
import asyncio
import arequest

async def main():
    # Session with default headers
    async with arequest.Session(
        headers={'User-Agent': 'MyApp/1.0'},
        auth=arequest.BasicAuth('username', 'password')
    ) as session:
        # Override headers for specific request
        response = await session.get(
            'https://api.example.com/data',
            headers={'X-Custom-Header': 'value'}
        )
        print(response.json())

asyncio.run(main())
```

### SSL Configuration

```python
import asyncio
import arequest

async def main():
    # Disable SSL verification (not recommended for production)
    async with arequest.Session(verify=False) as session:
        response = await session.get('https://self-signed.example.com/data')
        print(response.status_code)

asyncio.run(main())
```

### Timeouts

```python
import asyncio
import arequest

async def main():
    # Session-level timeout
    async with arequest.Session(timeout=10.0) as session:
        response = await session.get('https://httpbin.org/delay/2')
    
    # Request-level timeout (overrides session)
    async with arequest.Session() as session:
        response = await session.get('https://httpbin.org/delay/2', timeout=5.0)

asyncio.run(main())
```

---

## Performance Considerations

1. **Reuse Sessions**: Always use [`Session`](../src/arequest/client.py:355) for multiple requests to benefit from connection pooling.

2. **Concurrent Requests**: Use [`bulk_get()`](../src/arequest/client.py:644) or [`gather()`](../src/arequest/client.py:609) instead of sequential requests for better throughput.

3. **Connection Limits**: Adjust `connector_limit` and `connector_limit_per_host` based on your use case:
   - Lower values for rate-limited APIs
   - Higher values for internal services

4. **Parser Optimization**: Install `httptools` for C-accelerated HTTP parsing:
   ```bash
   pip install httptools
   ```

5. **Event Loop**: On Linux/macOS, use `uvloop` for better performance:
   ```bash
   pip install uvloop
   ```

---

## See Also

- [`auth.md`](auth.md) - Authentication handlers
- [`parser.md`](parser.md) - HTTP parsing implementation
- [`api.md`](api.md) - Public API reference
