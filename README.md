# arequest

**High-performance async HTTP client for Python**

[![PyPI version](https://badge.fury.io/py/arequest.svg)](https://badge.fury.io/py/arequest)
[![Python versions](https://img.shields.io/pypi/pyversions/arequest.svg)](https://pypi.org/project/arequest/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

**arequest** is a fast asynchronous HTTP client that works like `requests` but uses Python's async/await. It's designed for speed with connection pooling, optimized parsing, and concurrent request handling.

### Key Features

- 🚀 Fast async I/O with connection pooling
- 🔄 Requests-compatible API - familiar and easy to use
- ⚡ Handle hundreds of concurrent requests
- 📦 Optional C-accelerated parsing with httptools
- 🎨 Full type hints throughout

---

## Performance

Real-world benchmark (50 requests to httpbin.org):

| Library | Mode | Requests/sec |
|---------|------|--------------|
| **arequest** | concurrent | **24.10** |
| arequest | sequential | 2.30 |
| requests | with session | 2.28 |
| aiohttp | concurrent | 24.24 |

arequest concurrent mode is ~10x faster than standard requests library.

---

## Installation

```bash
pip install arequest

# For best performance, install optional dependencies:
pip install httptools  # faster HTTP parsing
```

---

## Quick Start

### Simple Request

```python
import asyncio
import arequest

async def main():
    response = await arequest.get("https://httpbin.org/get")
    print(response.json())

asyncio.run(main())
```

### Using Sessions (Recommended)

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        response = await session.get("https://httpbin.org/get")
        print(response.status_code)
        print(response.text)

asyncio.run(main())
```

### Concurrent Requests

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Make 100 requests concurrently
        urls = [f"https://httpbin.org/get?i={i}" for i in range(100)]
        responses = await session.bulk_get(urls)
        
        for response in responses:
            print(f"Status: {response.status_code}")

asyncio.run(main())
```

---

## Usage Examples

### POST with JSON

```python
async def main():
    data = {'name': 'Alice', 'email': 'alice@example.com'}
    response = await arequest.post('https://httpbin.org/post', json=data)
    print(response.json())
```

### Custom Headers

```python
async def main():
    headers = {'Authorization': 'Bearer token123'}
    response = await arequest.get('https://api.example.com', headers=headers)
```

### Query Parameters

```python
async def main():
    params = {'page': 1, 'limit': 100}
    response = await arequest.get('https://api.example.com', params=params)
```

### Error Handling

```python
async def main():
    try:
        response = await arequest.get('https://httpbin.org/status/404')
        response.raise_for_status()
    except arequest.ClientError as e:
        print(f"Error: {e}")
```

### Authentication

```python
from arequest import BasicAuth

async def main():
    auth = BasicAuth('username', 'password')
    response = await arequest.get('https://httpbin.org/basic-auth/username/password', auth=auth)
```

---

## API Reference

### Response Object

```python
response.status_code    # HTTP status code
response.headers        # Response headers dict
response.url           # Final URL
response.content       # Raw bytes
response.text          # Decoded text
response.json()        # Parse JSON
response.ok            # True if status < 400
response.raise_for_status()  # Raise on error
```

### Session Options

```python
session = arequest.Session(
    headers={'User-Agent': 'MyApp/1.0'},
    timeout=30.0,
    verify=True
)
```

### Request Methods

All standard HTTP methods are supported:
- `get(url, **kwargs)`
- `post(url, **kwargs)`
- `put(url, **kwargs)`
- `delete(url, **kwargs)`
- `patch(url, **kwargs)`
- `head(url, **kwargs)`
- `options(url, **kwargs)`

---

## Performance Tips

1. Use `Session` for multiple requests to reuse connections
2. Use concurrent requests with `asyncio.gather()` or `bulk_get()`
3. Install `httptools` for faster parsing: `pip install httptools`

---

## Requirements

- Python 3.9+
- Optional: httptools for faster parsing

---

## License

MIT License - see LICENSE file

---

## Author

**Abhra** - [@abhrajyoti-01](https://github.com/abhrajyoti-01)

- **Connection Pooling**: Reuse connections across multiple requests
- **DNS Caching**: 60-second TTL reduces DNS lookup overhead
- **Keep-Alive**: Persistent connections reduce TCP handshake overhead
- **C-Accelerated Parsing**: Optional `httptools` support for 2-5x faster parsing
- **Zero-Copy Buffer Management**: Minimizes memory allocations and copies
- **TCP_NODELAY**: Optimized for low-latency communication

---

## Features

### Core Features

- ✅ **High-performance connection pooling** with configurable limits
- ✅ **Requests-like API** with full async/await support
- ✅ **Optional C-accelerated parsing** via `httptools`
- ✅ **DNS caching** and **keep-alive** connection reuse
- ✅ **Simple concurrency helpers** (`bulk_get`, `gather`)
- ✅ **Full type hints** throughout the codebase
- ✅ **Minimal dependencies** - only standard library required

### HTTP Features

- ✅ All HTTP methods: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS
- ✅ Automatic redirect following with configurable limits
- ✅ SSL/TLS support with certificate verification
- ✅ Chunked transfer encoding support
- ✅ Custom headers and query parameters
- ✅ JSON and form data handling
- ✅ Request and response streaming

### Authentication

- ✅ HTTP Basic Authentication
- ✅ Bearer Token Authentication
- ✅ Custom authentication handlers via extensible base class

### Error Handling

- ✅ Comprehensive exception hierarchy
- ✅ Client errors (4xx) with [`ClientError`](docs/api.md#clienterror)
- ✅ Server errors (5xx) with [`ServerError`](docs/api.md#servererror)
- ✅ Timeout errors with [`TimeoutError`](docs/api.md#timeouterror)
- ✅ Automatic status code checking with [`raise_for_status()`](docs/client.md#raise_for_status)

---

## Installation

### Basic Installation

```bash
pip install arequest
```

### With Performance Extras

For optimal performance, install the optional dependencies:

```bash
# Faster HTTP parsing (C extension) - Recommended
pip install arequest[fast]

# Faster event loop on Linux/macOS
pip install arequest[uvloop]

# Install all performance extras
pip install arequest[all]
```

Or install dependencies manually:

```bash
# Faster HTTP parsing (C extension)
pip install httptools

# Faster event loop on Linux/macOS
pip install uvloop
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/abhrajyoti-01/arequest.git
cd arequest

# Install in development mode with dev dependencies
pip install -e .[dev]

# Run tests
pytest

# Run linting
ruff check src/
```

### Requirements

- Python 3.9 or higher
- asyncio (included in Python 3.7+)
- Optional: httptools (for C-accelerated parsing)
- Optional: uvloop (for faster event loop on Linux/macOS)

---

## Quick Start

### Simple Request

Make a simple GET request with automatic session management:

```python
import asyncio
import arequest

async def main():
    response = await arequest.get("https://httpbin.org/get")
    print(response.json())

asyncio.run(main())
```

### Using Sessions (Recommended)

For multiple requests, use a [`Session`](docs/client.md#session) to benefit from connection pooling.

**Requests-like Session Creation:**

If you're familiar with the `requests` library, arequest follows a similar pattern:

```python
# requests library (synchronous)
import requests

# Create session
session = requests.Session()

# Make requests
response = session.get("https://httpbin.org/get")
print(response.status_code)

# Close session when done
session.close()
```

```python
# arequest (asynchronous)
import asyncio
import arequest

async def main():
    # Create session (same as requests)
    session = arequest.Session()
    
    try:
        # Make requests (await required)
        response = await session.get("https://httpbin.org/get")
        print(response.status_code)
        
        # Connection is reused across requests
        response = await session.post(
            "https://httpbin.org/post",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        data = response.json()
        print(data)
    finally:
        # Close session when done (same as requests)
        await session.close()

asyncio.run(main())
```

**Using Context Manager (Recommended):**

```python
import asyncio
import arequest

async def main():
    # Context manager automatically handles session lifecycle
    async with arequest.Session() as session:
        # Connection is reused across requests
        response = await session.get("https://httpbin.org/get")
        print(response.status_code)
        print(response.text)

        response = await session.post(
            "https://httpbin.org/post",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        data = response.json()
        print(data)

asyncio.run(main())
```

**Session with Configuration (requests-like):**

```python
import asyncio
import arequest

async def main():
    # Configure session with defaults (similar to requests)
    session = arequest.Session(
        headers={"User-Agent": "MyApp/1.0"},      # Like requests.Session.headers
        timeout=30.0,                             # Custom timeout
        verify=True,                                 # SSL verification
        auth=arequest.BasicAuth("user", "pass")      # Like requests.auth
    )
    
    async with session:
        response = await session.get("https://httpbin.org/get")
        print(response.json())

asyncio.run(main())
```

**Comparison: requests vs arequest**

| Feature | requests (sync) | arequest (async) |
|----------|-----------------|------------------|
| Create session | `session = requests.Session()` | `session = arequest.Session()` |
| Make request | `response = session.get(url)` | `response = await session.get(url)` |
| Close session | `session.close()` | `await session.close()` |
| Context manager | `with requests.Session() as s:` | `async with arequest.Session() as s:` |
| Headers | `session.headers.update({...})` | `session = arequest.Session(headers={...})` |
| Auth | `session.auth = (user, pass)` | `session = arequest.Session(auth=BasicAuth(user, pass))` |
| Timeout | `response = session.get(url, timeout=30)` | `response = await session.get(url, timeout=30)` |

### Concurrent Requests

Execute multiple requests concurrently for maximum performance:

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Method 1: Using bulk_get for multiple GET requests
        urls = [f"https://httpbin.org/get?i={i}" for i in range(100)]
        responses = await session.bulk_get(urls)

        # Method 2: Using gather for mixed HTTP methods
        responses = await session.gather(
            ("GET", "https://httpbin.org/get"),
            ("POST", "https://httpbin.org/post"),
            "https://httpbin.org/uuid",  # Defaults to GET
        )

        # Method 3: Using asyncio.gather manually
        tasks = [session.get(f"https://httpbin.org/get?i={i}") for i in range(100)]
        responses = await asyncio.gather(*tasks)

asyncio.run(main())
```

### Sequential Requests

Execute multiple requests sequentially (one after another):

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Sequential requests - one after another
        for i in range(10):
            response = await session.get(f"https://httpbin.org/get?i={i}")
            print(f"Request {i}: {response.status_code}")

asyncio.run(main())
```

**When to use sequential requests:**
- When requests depend on previous responses
- When you need to process each response before making the next request
- When rate limiting requires sequential execution
- When order matters and you need results in sequence

**Sequential vs Concurrent:**

```python
import asyncio
import arequest
import time

async def sequential_requests():
    """Requests execute one after another."""
    start = time.time()
    async with arequest.Session() as session:
        for i in range(5):
            response = await session.get(f"https://httpbin.org/delay/1?i={i}")
            print(f"Sequential {i}: {response.status_code}")
    return time.time() - start

async def concurrent_requests():
    """Requests execute in parallel."""
    start = time.time()
    async with arequest.Session() as session:
        tasks = [session.get(f"https://httpbin.org/delay/1?i={i}") for i in range(5)]
        responses = await asyncio.gather(*tasks)
        for i, response in enumerate(responses):
            print(f"Concurrent {i}: {response.status_code}")
    return time.time() - start

async def main():
    print("Sequential requests:")
    seq_time = await sequential_requests()
    print(f"Total time: {seq_time:.2f}s\n")
    
    print("Concurrent requests:")
    conc_time = await concurrent_requests()
    print(f"Total time: {conc_time:.2f}s\n")
    
    print(f"Speedup: {seq_time/conc_time:.2f}x")

asyncio.run(main())
```

**Sequential requests with different HTTP methods:**

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Sequential requests using different HTTP methods
        # Each request waits for the previous one to complete
        
        # Step 1: Create a resource
        create_response = await session.post(
            "https://jsonplaceholder.typicode.com/posts",
            json={
                "title": "My Post",
                "body": "This is the post content",
                "userId": 1
            }
        )
        created_post = create_response.json()
        post_id = created_post['id']
        print(f"Created post with ID: {post_id}")
        
        # Step 2: Read the created resource
        read_response = await session.get(
            f"https://jsonplaceholder.typicode.com/posts/{post_id}"
        )
        post = read_response.json()
        print(f"Read post: {post['title']}")
        
        # Step 3: Update the resource
        update_response = await session.put(
            f"https://jsonplaceholder.typicode.com/posts/{post_id}",
            json={
                "id": post_id,
                "title": "Updated Post",
                "body": "This is the updated content",
                "userId": 1
            }
        )
        updated_post = update_response.json()
        print(f"Updated post: {updated_post['title']}")
        
        # Step 4: Partial update using PATCH
        patch_response = await session.patch(
            f"https://jsonplaceholder.typicode.com/posts/{post_id}",
            json={"title": "Partially Updated Post"}
        )
        patched_post = patch_response.json()
        print(f"Patched post: {patched_post['title']}")
        
        # Step 5: Delete the resource
        delete_response = await session.delete(
            f"https://jsonplaceholder.typicode.com/posts/{post_id}"
        )
        print(f"Deleted post - Status: {delete_response.status_code}")

asyncio.run(main())
```

**Sequential requests using the generic request() method:**

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Using the generic request() method for sequential operations
        
        methods = ['GET', 'POST', 'PUT', 'DELETE']
        url = "https://httpbin.org/anything"
        
        for method in methods:
            # Each request waits for the previous one
            response = await session.request(
                method,
                url,
                json={"method": method}
            )
            print(f"{method}: {response.status_code} - {response.json()['method']}")

asyncio.run(main())
```

**Sequential requests with error handling:**

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        urls = [
            "https://jsonplaceholder.typicode.com/posts/1",
            "https://jsonplaceholder.typicode.com/posts/2",
            "https://jsonplaceholder.typicode.com/posts/9999",  # Will fail
            "https://jsonplaceholder.typicode.com/posts/3"
        ]
        
        for url in urls:
            try:
                response = await session.get(url)
                print(f"✓ {url}: {response.status_code}")
            except arequest.ClientError as e:
                print(f"✗ {url}: Client error {e.status_code}")
            except arequest.ServerError as e:
                print(f"✗ {url}: Server error {e.status_code}")
            except arequest.TimeoutError:
                print(f"✗ {url}: Request timed out")
            except Exception as e:
                print(f"✗ {url}: {e}")

asyncio.run(main())
```

**Sequential requests with data processing:**

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Step 1: Get list of users
        users_response = await session.get("https://jsonplaceholder.typicode.com/users")
        users = users_response.json()
        
        # Step 2: Process each user sequentially
        for user in users[:3]:  # Process first 3 users
            print(f"\nProcessing user: {user['name']}")
            
            # Step 3: Get user's posts
            posts_response = await session.get(
                f"https://jsonplaceholder.typicode.com/posts?userId={user['id']}"
            )
            posts = posts_response.json()
            
            print(f"  Found {len(posts)} posts")
            
            # Step 4: Process each post
            for post in posts[:2]:  # Process first 2 posts
                print(f"    - {post['title'][:40]}...")
                
                # Step 5: Get post comments
                comments_response = await session.get(
                    f"https://jsonplaceholder.typicode.com/comments?postId={post['id']}"
                )
                comments = comments_response.json()
                print(f"      {len(comments)} comments")

asyncio.run(main())
```

---

## Examples

### HTTP Methods

All standard HTTP methods are supported:

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # GET
        response = await session.get("https://httpbin.org/get")
        print(f"GET: {response.status_code}")

        # POST with JSON
        response = await session.post(
            "https://httpbin.org/post",
            json={"key": "value"}
        )
        print(f"POST: {response.status_code}")

        # PUT
        response = await session.put(
            "https://httpbin.org/put",
            data="raw data"
        )
        print(f"PUT: {response.status_code}")

        # PATCH
        response = await session.patch(
            "https://httpbin.org/patch",
            json={"update": "field"}
        )
        print(f"PATCH: {response.status_code}")

        # DELETE
        response = await session.delete("https://httpbin.org/delete")
        print(f"DELETE: {response.status_code}")

        # HEAD
        response = await session.head("https://httpbin.org/get")
        print(f"HEAD: {response.status_code}")

        # OPTIONS
        response = await session.options("https://httpbin.org/get")
        print(f"OPTIONS: {response.status_code}")

asyncio.run(main())
```

### Request Parameters

#### Custom Headers

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        response = await session.get(
            "https://httpbin.org/headers",
            headers={
                "User-Agent": "MyApp/1.0",
                "Accept": "application/json",
                "X-Custom-Header": "custom-value"
            }
        )
        print(response.json())

asyncio.run(main())
```

#### Query Parameters

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        response = await session.get(
            "https://httpbin.org/get",
            params={
                "key1": "value1",
                "key2": "value2",
                "page": 2,
                "limit": 10
            }
        )
        print(response.json())

asyncio.run(main())
```

#### Form Data

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Form-encoded data
        response = await session.post(
            "https://httpbin.org/post",
            data={
                "username": "user",
                "password": "pass",
                "remember": "on"
            }
        )
        print(response.json())

asyncio.run(main())
```

#### Raw Body

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Raw string body
        response = await session.post(
            "https://httpbin.org/post",
            data="raw body content"
        )
        print(response.json())

        # Raw bytes body
        response = await session.post(
            "https://httpbin.org/post",
            data=b"binary data"
        )
        print(response.json())

asyncio.run(main())
```

### Response Handling

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        response = await session.get("https://httpbin.org/get")

        # Access response properties
        print(f"Status Code: {response.status_code}")
        print(f"Reason: {response.reason}")
        print(f"URL: {response.url}")
        print(f"Headers: {response.headers}")
        print(f"Encoding: {response.encoding}")
        print(f"Elapsed: {response.elapsed:.3f}s")
        print(f"OK: {response.ok}")

        # Access response body
        print(f"Content (bytes): {response.content[:50]}...")
        print(f"Text: {response.text[:100]}...")

        # Parse JSON
        data = response.json()
        print(f"JSON: {data}")

        # Check status
        if response.ok:
            print("Request successful!")
        else:
            response.raise_for_status()

asyncio.run(main())
```

### Authentication

#### Basic Authentication

```python
import asyncio
import arequest

async def main():
    auth = arequest.BasicAuth("username", "password")

    async with arequest.Session(auth=auth) as session:
        response = await session.get("https://httpbin.org/basic-auth/username/password")
        print(f"Status: {response.status_code}")
        print(f"Authenticated: {response.json()['authenticated']}")

asyncio.run(main())
```

#### Bearer Token Authentication

```python
import asyncio
import arequest

async def main():
    auth = arequest.BearerAuth("your-token-here")

    async with arequest.Session(auth=auth) as session:
        response = await session.get("https://httpbin.org/bearer")
        print(f"Status: {response.status_code}")
        print(response.json())

asyncio.run(main())
```

#### Custom Authentication

```python
import asyncio
import arequest
from arequest.auth import AuthBase

class APIKeyAuth(AuthBase):
    """Custom API key authentication."""
    
    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self.api_key = api_key
        self.header_name = header_name
    
    def apply(self, request):
        request.headers[self.header_name] = self.api_key

async def main():
    auth = APIKeyAuth("my-secret-api-key")

    async with arequest.Session(auth=auth) as session:
        response = await session.get("https://httpbin.org/headers")
        print(response.json())

asyncio.run(main())
```

### Timeouts

```python
import asyncio
import arequest

async def main():
    # Request-level timeout
    async with arequest.Session() as session:
        response = await session.get(
            "https://httpbin.org/delay/1",
            timeout=5.0
        )
        print(f"Status: {response.status_code}")

    # Session-level timeout
    async with arequest.Session(timeout=30.0) as session:
        response = await session.get("https://httpbin.org/get")
        print(f"Status: {response.status_code}")

asyncio.run(main())
```

### SSL Configuration

```python
import asyncio
import arequest

async def main():
    # Disable SSL verification (not recommended for production)
    async with arequest.Session(verify=False) as session:
        response = await session.get("https://self-signed.example.com/data")
        print(f"Status: {response.status_code}")

    # Request-level SSL verification
    async with arequest.Session() as session:
        response = await session.get(
            "https://self-signed.example.com/data",
            verify=False
        )
        print(f"Status: {response.status_code}")

asyncio.run(main())
```

### Redirects

```python
import asyncio
import arequest

async def main():
    # Follow redirects (default)
    async with arequest.Session() as session:
        response = await session.get("https://httpbin.org/redirect/1")
        print(f"Final URL: {response.url}")
        print(f"Status: {response.status_code}")

    # Disable redirects
    async with arequest.Session() as session:
        response = await session.get(
            "https://httpbin.org/redirect/1",
            allow_redirects=False
        )
        print(f"Redirect status: {response.status_code}")
        print(f"Location: {response.headers.get('Location')}")

    # Custom redirect limit
    async with arequest.Session() as session:
        response = await session.get(
            "https://httpbin.org/redirect/5",
            max_redirects=3
        )
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
            response = await session.get("https://httpbin.org/status/404")
            response.raise_for_status()
        except arequest.ClientError as e:
            print(f"Client error: {e.status_code}")
        except arequest.ServerError as e:
            print(f"Server error: {e.status_code}")
        except arequest.TimeoutError:
            print("Request timed out")
        except Exception as e:
            print(f"Unexpected error: {e}")

asyncio.run(main())
```

### Session Configuration

```python
import asyncio
import arequest

async def main():
    # Configure session with defaults
    session = arequest.Session(
        headers={"User-Agent": "MyApp/1.0"},
        timeout=30.0,
        connector_limit=100,
        connector_limit_per_host=30,
        verify=True,
        auth=arequest.BasicAuth("user", "pass")
    )

    async with session:
        response = await session.get("https://httpbin.org/get")
        print(response.json())

asyncio.run(main())
```

### Advanced Concurrency

```python
import asyncio
import arequest

async def fetch_user(session, user_id):
    """Fetch a single user."""
    response = await session.get(f"https://jsonplaceholder.typicode.com/users/{user_id}")
    return response.json()

async def fetch_users_concurrently():
    """Fetch multiple users concurrently."""
    async with arequest.Session() as session:
        # Create tasks for all users
        tasks = [fetch_user(session, i) for i in range(1, 11)]
        
        # Execute all tasks concurrently
        users = await asyncio.gather(*tasks)
        
        # Process results
        for user in users:
            print(f"User: {user['name']}")

asyncio.run(fetch_users_concurrently())
```

### Rate Limiting

```python
import asyncio
import arequest

async def fetch_with_rate_limit(urls, rate_limit=10):
    """Fetch URLs with rate limiting."""
    semaphore = asyncio.Semaphore(rate_limit)
    
    async def fetch(session, url):
        async with semaphore:
            return await session.get(url)
    
    async with arequest.Session() as session:
        tasks = [fetch(session, url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return responses

async def main():
    urls = [f"https://httpbin.org/get?i={i}" for i in range(100)]
    responses = await fetch_with_rate_limit(urls, rate_limit=10)
    print(f"Fetched {len(responses)} URLs")

asyncio.run(main())
```

---

## API Overview

### Response Object

The [`Response`](docs/client.md#response) object provides access to all response data:

```python
response = await session.get("https://httpbin.org/get")

# Properties
response.status_code    # int: HTTP status code
response.headers        # dict[str, str]: Response headers
response.url            # str: Requested URL
response.content        # bytes: Raw response body
response.text           # str: Decoded response body
response.encoding       # str: Character encoding
response.reason         # str: HTTP reason phrase
response.elapsed        # float: Request duration in seconds
response.ok             # bool: True if status code < 400

# Methods
response.json()         # Parse response body as JSON
response.decode()       # Decode response body with optional encoding
response.raise_for_status()  # Raise exception for 4xx/5xx status codes
```

### Session Options

Configure a [`Session`](docs/client.md#session) with default behavior:

```python
session = arequest.Session(
    headers={"User-Agent": "MyApp/1.0"},      # Default headers
    timeout=30.0,                             # Default timeout
    connector_limit=100,                      # Total connection limit
    connector_limit_per_host=30,              # Per-host connection limit
    auth=arequest.BasicAuth("user", "pass"),  # Default authentication
    verify=True                                # SSL verification
)
```

### Request Parameters

All request methods accept the following parameters:

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

---

## Performance Tips

1. **Reuse Sessions**: Always use [`Session`](docs/client.md#session) for multiple requests to benefit from connection pooling
2. **Concurrent Requests**: Use [`bulk_get()`](docs/client.md#bulk_geturls-kwargs) or [`gather()`](docs/client.md#gatherrequests-kwargs) instead of sequential requests
3. **Install httptools**: Get 2-5x faster parsing with `pip install httptools`
4. **Use uvloop**: On Linux/macOS, install `uvloop` for better event loop performance
5. **Adjust Connection Limits**: Tune `connector_limit` and `connector_limit_per_host` for your use case
6. **Enable Keep-Alive**: Connections are kept alive by default for better performance
7. **Use Appropriate Timeouts**: Set timeouts to prevent hanging on slow responses

---

## Documentation

For detailed documentation, see:

- **[Documentation Index](docs/index.md)** - Complete documentation overview
- **[API Reference](docs/api.md)** - Complete API reference for all classes, functions, and exceptions
- **[Client Module](docs/client.md)** - HTTP client, session management, and response handling
- **[Authentication](docs/auth.md)** - Authentication handlers and custom implementations
- **[Parser Module](docs/parser.md)** - HTTP parsing implementation with C-acceleration support

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Ensure code passes linting (`ruff check src/`)
5. Ensure tests pass (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Setup

```bash
# Clone the repository
git clone https://github.com/abhrajyoti-01/arequest.git
cd arequest

# Install in development mode
pip install -e .[dev]

# Run tests
pytest

# Run linting
ruff check src/

# Format code
ruff format src/
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Author

**Abhra**

- GitHub: [@abhrajyoti-01](https://github.com/abhrajyoti-01)

---

## Acknowledgments

- Built with Python's [`asyncio`](https://docs.python.org/3/library/asyncio.html)
- Optional parsing acceleration via [`httptools`](https://github.com/MagicStack/httptools)
- Inspired by [`requests`](https://requests.readthedocs.io/) and [`aiohttp`](https://docs.aiohttp.org/)

---

<div align="center">

**If you find arequest useful, please consider giving it a ⭐ on GitHub!**

[⬆ Back to Top](#arequest)

</div>
