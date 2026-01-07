# AsyncReq Documentation

Welcome to the AsyncReq documentation. AsyncReq is a high-performance async HTTP client with a requests-like API, designed for low overhead and a familiar developer experience.

## Table of Contents

- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Features](#features)
- [Installation](#installation)
- [Performance](#performance)

---

## Quick Start

### Installation

```bash
pip install arequest
```

Optional performance extras:

```bash
# Faster HTTP parsing (C extension)
pip install httptools

# Faster event loop on Linux/macOS
pip install uvloop
```

### Basic Usage

```python
import asyncio
import arequest

async def main():
    # Simple one-off request
    response = await arequest.get('https://httpbin.org/get')
    print(response.json())
    
    # Using session for connection reuse (recommended)
    async with arequest.Session() as session:
        resp = await session.get('https://httpbin.org/get')
        print(resp.status_code)
        
        # Concurrent requests
        tasks = [session.get(f'https://httpbin.org/get?i={i}') for i in range(10)]
        responses = await asyncio.gather(*tasks)

asyncio.run(main())
```

---

## Documentation

### Core Modules

- **[API Reference](api.md)** - Complete API reference for all public classes, functions, and exceptions
- **[Client Module](client.md)** - HTTP client, session management, and response handling
- **[Authentication](auth.md)** - Authentication handlers (Basic, Bearer, custom implementations)
- **[Parser Module](parser.md)** - HTTP parsing implementation with C-acceleration support

### Getting Started

1. **[Quick Start Guide](#quick-start)** - Get up and running in minutes
2. **[API Reference](api.md)** - Explore all available methods and classes
3. **[Client Module](client.md)** - Learn about sessions and connection pooling
4. **[Authentication](auth.md)** - Implement authentication for your requests
5. **[Examples](#examples)** - Practical code examples

---

## Features

### High Performance

- **Connection Pooling**: Reuse connections for multiple requests
- **Concurrent Requests**: Execute multiple requests in parallel
- **C-Accelerated Parsing**: Optional `httptools` support for 2-5x faster parsing
- **DNS Caching**: Reduce DNS lookup overhead
- **Keep-Alive Support**: Maintain persistent connections

### Developer Friendly

- **Requests-like API**: Familiar interface from the popular `requests` library
- **Type Hints**: Full type annotations for better IDE support
- **Async/Await**: Native Python async/await support
- **Simple Concurrency**: Easy-to-use helpers like `bulk_get()` and `gather()`
- **Minimal Dependencies**: Core functionality with no external dependencies

### Production Ready

- **SSL/TLS Support**: Full HTTPS support with certificate verification
- **Error Handling**: Comprehensive exception hierarchy
- **Timeout Management**: Configurable timeouts at session and request level
- **Redirect Handling**: Automatic redirect following with configurable limits
- **Connection Limits**: Per-host and total connection limits

---

## Installation

### Basic Installation

```bash
pip install arequest
```

### With Performance Extras

```bash
# Install with httptools for faster parsing
pip install arequest[fast]

# Install with uvloop for faster event loop (Linux/macOS only)
pip install arequest[uvloop]

# Install all performance extras
pip install arequest[all]
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/abhrajyoti-01/arequest.git
cd arequest

# Install in development mode
pip install -e .[dev]

# Run tests
pytest
```

---

## Performance

### Benchmarks

Example benchmark (50 concurrent requests, local test server):

```
Library                     Requests/sec
arequest (bulk_get)          24.49
arequest (concurrent)        18.61
aiohttp                      18.38
```

### Performance Tips

1. **Reuse Sessions**: Always use [`Session`](client.md#session) for multiple requests
2. **Concurrent Requests**: Use [`bulk_get()`](client.md#bulk_geturls-kwargs) or [`gather()`](client.md#gatherrequests-kwargs) instead of sequential requests
3. **Install httptools**: Get 2-5x faster parsing with `pip install httptools`
4. **Use uvloop**: On Linux/macOS, install `uvloop` for better event loop performance
5. **Adjust Connection Limits**: Tune `connector_limit` and `connector_limit_per_host` for your use case

---

## Examples

### Simple Request

```python
import asyncio
import arequest

async def main():
    response = await arequest.get('https://httpbin.org/get')
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

### Concurrent Requests

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Fetch 100 URLs concurrently
        urls = [f'https://httpbin.org/get?i={i}' for i in range(100)]
        responses = await session.bulk_get(urls)
        
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
            json={'name': 'Alice', 'email': 'alice@example.com'}
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
    auth = arequest.BasicAuth('username', 'password')
    
    async with arequest.Session(auth=auth) as session:
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

---

## Support

- **GitHub Issues**: [Report bugs and request features](https://github.com/abhrajyoti-01/arequest/issues)
- **Documentation**: [Full API reference](api.md)
- **Examples**: See [`example_basic.py`](../example_basic.py) and [`example_session.py`](../example_session.py) for more code samples

---

## License

MIT License - see [LICENSE](../LICENSE) for details.

---

## Contributing

Contributions are welcome! Please open a pull request with a clear description of your changes.

For development setup:

```bash
# Install development dependencies
pip install -e .[dev]

# Run tests
pytest

# Run linting
ruff check src/
```

---

## Acknowledgments

- Built with Python's asyncio
- Optional parsing acceleration via [httptools](https://github.com/MagicStack/httptools)
- Inspired by [requests](https://requests.readthedocs.io/) and [aiohttp](https://docs.aiohttp.org/)
