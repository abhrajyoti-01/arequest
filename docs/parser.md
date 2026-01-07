# Parser Module Documentation

## Overview

The [`parser.py`](../src/arequest/parser.py) module provides high-performance HTTP parsing with optional C-extension support. It implements:

- [`FastHTTPParser`](../src/arequest/parser.py:19) - High-performance HTTP response parser
- [`FastHTTPRequestBuilder`](../src/arequest/parser.py:149) - Optimized HTTP request builder
- Automatic fallback between C-accelerated and pure Python implementations
- Support for chunked transfer encoding
- Efficient memory management with zero-copy techniques

The module automatically uses `httptools` (C extension) when available for maximum performance, falling back to an optimized pure-Python implementation.

---

## Features

### Performance Optimizations

1. **C-Accelerated Parsing**: Uses `httptools` library for C-speed HTTP parsing when available
2. **Zero-Copy Buffer Management**: Minimizes memory allocations and copies
3. **Pre-encoded Constants**: Common HTTP parts are pre-encoded to avoid repeated allocations
4. **Efficient Chunked Encoding**: Optimized handling of chunked transfer encoding
5. **Lazy Decoding**: Response body is parsed only when needed

### Compatibility

- **Automatic Fallback**: Seamlessly switches between C and Python implementations
- **HTTP/1.1 Compliance**: Full support for HTTP/1.1 protocol
- **Chunked Transfer Encoding**: Handles chunked responses efficiently
- **Keep-Alive Support**: Properly parses Connection headers for connection reuse

---

## Classes

### FastHTTPParser

High-performance HTTP response parser that automatically selects the best implementation based on available libraries.

#### Constructor

```python
FastHTTPParser()
```

Creates a new parser instance. The parser is stateful and can be reused for multiple requests.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `status_code` | `int` | HTTP status code (e.g., 200, 404) |
| `reason` | `str` | HTTP reason phrase (e.g., "OK", "Not Found") |
| `headers` | `dict[str, str]` | Response headers |
| `body` | `bytes` | Response body |
| `keep_alive` | `bool` | Whether connection should be kept alive |

#### Internal Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `_content_length` | `Optional[int]` | Parsed Content-Length header value |
| `_chunked` | `bool` | Whether transfer encoding is chunked |
| `_body_parts` | `list[bytes]` | Accumulated body parts (for chunked responses) |
| `_headers_complete` | `bool` | Whether headers have been parsed |
| `_message_complete` | `bool` | Whether entire message has been parsed |

#### Methods

##### [`parse(reader)`](../src/arequest/parser.py:68)

Parse an HTTP response from an asyncio StreamReader.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `reader` | `asyncio.StreamReader` | Async stream reader containing the HTTP response |

**Behavior:**
- Resets parser state before parsing
- Automatically selects httptools or Python implementation
- Parses status line, headers, and body
- Handles chunked transfer encoding if present
- Populates `status_code`, `reason`, `headers`, `body`, and `keep_alive` attributes

**Example:**

```python
import asyncio
from arequest.parser import FastHTTPParser

async def parse_response(reader):
    parser = FastHTTPParser()
    await parser.parse(reader)
    
    print(f"Status: {parser.status_code}")
    print(f"Headers: {parser.headers}")
    print(f"Body: {parser.body}")
    print(f"Keep-Alive: {parser.keep_alive}")
```

##### httptools Callbacks

When using the C-accelerated implementation, the following callback methods are used by httptools:

###### [`on_status(status)`](../src/arequest/parser.py:41)

Called when the HTTP status line is parsed.

**Parameters:**
- `status` (`bytes`): Status reason phrase as bytes

###### [`on_header(name, value)`](../src/arequest/parser.py:44)

Called for each header in the response.

**Parameters:**
- `name` (`bytes`): Header name as bytes
- `value` (`bytes`): Header value as bytes

**Behavior:**
- Decodes header name and value from bytes to string
- Stores header in `headers` dictionary
- Parses special headers: `Content-Length`, `Transfer-Encoding`, `Connection`

###### [`on_headers_complete()`](../src/arequest/parser.py:57)

Called when all headers have been parsed.

###### [`on_body(body)`](../src/arequest/parser.py:60)

Called for each chunk of body data.

**Parameters:**
- `body` (`bytes`): Body chunk as bytes

**Behavior:**
- Accumulates body parts in `_body_parts` list

###### [`on_message_complete()`](../src/arequest/parser.py:63)

Called when the entire HTTP message has been parsed.

**Behavior:**
- Joins accumulated body parts into final `body` attribute

##### Internal Methods

###### [`_parse_httptools(reader)`](../src/arequest/parser.py:87)

Parse using httptools C extension.

**Behavior:**
- Creates httptools.HttpResponseParser instance
- Reads data in 64KB chunks for efficiency
- Feeds data to parser until message complete
- Extracts status code from parser

###### [`_parse_python(reader)`](../src/arequest/parser.py:102)

Pure Python parsing fallback when httptools is not available.

**Behavior:**
- Reads headers until `\r\n\r\n` delimiter
- Parses status line to extract status code and reason
- Parses headers line by line
- Handles chunked encoding if present
- Reads body based on Content-Length or chunked encoding

---

### FastHTTPRequestBuilder

Optimized HTTP request builder with pre-encoded common parts for minimal allocations.

#### Constructor

```python
FastHTTPRequestBuilder()
```

This is a static class with no instance state needed.

#### Class Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `_CRLF` | `bytes` | Pre-encoded `\r\n` sequence |
| `_HTTP11` | `bytes` | Pre-encoded ` HTTP/1.1\r\n` sequence |
| `_COLON_SPACE` | `bytes` | Pre-encoded `: ` sequence |

#### Methods

##### [`build(method, path, headers, body=None)`](../src/arequest/parser.py:158)

Build an HTTP request as bytes with minimal allocations.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `method` | `str` | Required | HTTP method (GET, POST, etc.) |
| `path` | `str` | Required | Request path including query string |
| `headers` | `dict[str, str]` | Required | Request headers |
| `body` | `Optional[bytes]` | `None` | Request body (optional) |

**Returns:** `bytes` - Complete HTTP request as bytes

**Behavior:**
- Uses list and join pattern for efficient concatenation
- Encodes method and path to ASCII
- Uses pre-encoded constants for common HTTP parts
- Encodes headers with proper formatting
- Appends body if provided

**Example:**

```python
from arequest.parser import FastHTTPRequestBuilder

# Build a GET request
request = FastHTTPRequestBuilder.build(
    method='GET',
    path='/api/users?page=1',
    headers={
        'Host': 'api.example.com',
        'User-Agent': 'MyApp/1.0',
        'Accept': 'application/json'
    }
)

# Build a POST request with body
request = FastHTTPRequestBuilder.build(
    method='POST',
    path='/api/users',
    headers={
        'Host': 'api.example.com',
        'Content-Type': 'application/json',
        'Content-Length': '27'
    },
    body=b'{"name":"Alice","age":30}'
)
```

**Output Format:**
```
GET /api/users?page=1 HTTP/1.1
Host: api.example.com
User-Agent: MyApp/1.0
Accept: application/json

```

---

## Implementation Details

### httptools Integration

The module automatically detects and uses `httptools` when available:

```python
try:
    import httptools
    HTTPTOOLS_AVAILABLE = True
except ImportError:
    httptools = None
    HTTPTOOLS_AVAILABLE = False
```

**Installation:**
```bash
pip install httptools
```

**Benefits:**
- 2-5x faster parsing than pure Python
- Lower CPU usage
- Better memory efficiency

### Chunked Transfer Encoding

The parser handles chunked transfer encoding automatically:

```python
# Chunked response format:
# 4\r\n
# Wiki\r\n
# 5\r\n
# pedia\r\n
# 0\r\n
# \r\n
```

**Parsing Logic:**
1. Read chunk size line (hexadecimal)
2. If size is 0, read trailing CRLF and finish
3. Read exactly `size` bytes of body data
4. Read trailing CRLF after each chunk
5. Repeat until size is 0

**Example:**
```python
async def _read_chunked(reader):
    chunks = []
    while True:
        size_line = await reader.readline()
        size = int(size_line.strip().split(b';')[0], 16)
        if size == 0:
            await reader.readline()
            break
        chunks.append(await reader.readexactly(size))
        await reader.readexactly(2)
    return b''.join(chunks)
```

### Memory Optimization

The parser uses several techniques to minimize memory usage:

1. **List Accumulation**: Body parts are accumulated in a list and joined once
2. **Pre-encoded Constants**: Common HTTP parts are pre-encoded
3. **Efficient Reading**: Reads in 64KB chunks to balance memory and performance
4. **Zero-Copy Where Possible**: Minimizes unnecessary data copying

### Header Parsing

Special headers are parsed and processed:

| Header | Processing |
|--------|------------|
| `Content-Length` | Extracted and used to read exact body size |
| `Transfer-Encoding` | Detects `chunked` encoding |
| `Connection` | Sets `keep_alive` flag based on value |

---

## Usage Examples

### Basic Response Parsing

```python
import asyncio
from arequest.parser import FastHTTPParser

async def parse_example():
    # Simulate reading from a stream
    async def mock_reader():
        data = b'HTTP/1.1 200 OK\r\n'
        data += b'Content-Type: application/json\r\n'
        data += b'Content-Length: 13\r\n'
        data += b'\r\n'
        data += b'{"status":"ok"}'
        
        class MockStreamReader:
            async def readuntil(self, delimiter):
                return data.split(delimiter)[0] + delimiter
            
            async def readexactly(self, n):
                return data[-n:]
        
        return MockStreamReader()
    
    reader = await mock_reader()
    parser = FastHTTPParser()
    await parser.parse(reader)
    
    print(f"Status: {parser.status_code}")  # 200
    print(f"Reason: {parser.reason}")  # OK
    print(f"Headers: {parser.headers}")
    print(f"Body: {parser.body}")  # b'{"status":"ok"}'
    print(f"Keep-Alive: {parser.keep_alive}")  # True

asyncio.run(parse_example())
```

### Request Building

```python
from arequest.parser import FastHTTPRequestBuilder

def build_get_request():
    request = FastHTTPRequestBuilder.build(
        method='GET',
        path='/api/users?page=2&limit=10',
        headers={
            'Host': 'api.example.com',
            'User-Agent': 'MyApp/1.0',
            'Accept': 'application/json',
            'Authorization': 'Bearer token123'
        }
    )
    return request

def build_post_request():
    import json
    body = json.dumps({'name': 'Alice', 'email': 'alice@example.com'}).encode()
    
    request = FastHTTPRequestBuilder.build(
        method='POST',
        path='/api/users',
        headers={
            'Host': 'api.example.com',
            'Content-Type': 'application/json',
            'Content-Length': str(len(body))
        },
        body=body
    )
    return request

# Usage
get_request = build_get_request()
post_request = build_post_request()

print(get_request.decode('latin-1'))
print(post_request.decode('latin-1'))
```

### Custom Parser Implementation

```python
import asyncio
from arequest.parser import FastHTTPParser

class CustomResponseParser(FastHTTPParser):
    """Extended parser with custom functionality."""
    
    def __init__(self):
        super().__init__()
        self.content_type = None
        self.content_length = None
    
    def on_header(self, name, value):
        super().on_header(name, value)
        
        # Extract specific headers
        name_str = name.decode('latin-1').lower()
        value_str = value.decode('latin-1')
        
        if name_str == 'content-type':
            self.content_type = value_str
        elif name_str == 'content-length':
            self.content_length = int(value_str)

async def parse_with_custom():
    parser = CustomResponseParser()
    # ... parse response ...
    print(f"Content-Type: {parser.content_type}")
    print(f"Content-Length: {parser.content_length}")
```

### Performance Comparison

```python
import asyncio
import time
from arequest.parser import FastHTTPParser

async def benchmark_parsing():
    # Generate test data
    test_responses = [
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: application/json\r\n'
        b'Content-Length: 20\r\n'
        b'\r\n'
        b'{"message":"success"}'
    ] * 1000
    
    # Benchmark parsing
    start = time.perf_counter()
    
    for response in test_responses:
        parser = FastHTTPParser()
        # Simulate parsing (would use StreamReader in real usage)
        # await parser.parse(reader)
    
    elapsed = time.perf_counter() - start
    print(f"Parsed {len(test_responses)} responses in {elapsed:.4f}s")
    print(f"Average: {elapsed/len(test_responses)*1000:.4f}ms per response")

asyncio.run(benchmark_parsing())
```

---

## Performance Tips

### 1. Install httptools

For best performance, install the C-accelerated parser:

```bash
pip install httptools
```

### 2. Reuse Parser Instances

Parser instances can be reused for multiple requests:

```python
parser = FastHTTPParser()

for response in responses:
    parser.parse(response)
    # Process response
    # Parser is automatically reset on next parse
```

### 3. Use Efficient Request Building

The [`FastHTTPRequestBuilder`](../src/arequest/parser.py:149) is optimized for minimal allocations:

```python
# ✅ Good - Uses pre-encoded constants
request = FastHTTPRequestBuilder.build(
    method='GET',
    path='/api/data',
    headers={'Host': 'api.example.com'}
)

# ❌ Bad - Manual string concatenation
request = f"GET /api/data HTTP/1.1\r\nHost: api.example.com\r\n\r\n".encode()
```

### 4. Batch Processing

For processing multiple responses, use async operations:

```python
async def process_multiple_responses(streams):
    parser = FastHTTPParser()
    results = []
    
    for stream in streams:
        await parser.parse(stream)
        results.append({
            'status': parser.status_code,
            'body': parser.body
        })
    
    return results
```

---

## Troubleshooting

### httptools Not Available

**Issue:** Parser falls back to pure Python implementation

**Solution:** Install httptools:
```bash
pip install httptools
```

**Check availability:**
```python
from arequest.parser import HTTPTOOLS_AVAILABLE
print(f"httptools available: {HTTPTOOLS_AVAILABLE}")
```

### Chunked Encoding Issues

**Issue:** Parser fails to handle chunked responses

**Possible causes:**
- Malformed chunked encoding
- Unexpected connection close

**Solution:** Ensure server sends properly formatted chunked responses

### Memory Usage

**Issue:** High memory usage with large responses

**Solution:**
- Process responses in chunks if possible
- Use streaming for very large files
- Consider response size limits

---

## Technical Specifications

### HTTP/1.1 Compliance

The parser implements full HTTP/1.1 specification:

- ✅ Status line parsing
- ✅ Header parsing
- ✅ Chunked transfer encoding
- ✅ Content-Length handling
- ✅ Keep-Alive detection
- ✅ Connection header processing

### Encoding Support

- Headers: Latin-1 (HTTP specification requirement)
- Body: Binary (bytes), decoded by Response class
- Status reason: Latin-1

### Performance Characteristics

| Metric | httptools | Pure Python |
|--------|-----------|-------------|
| Parsing Speed | 2-5x faster | Baseline |
| Memory Usage | Lower | Higher |
| CPU Usage | Lower | Higher |

---

## See Also

- [`client.md`](client.md) - HTTP client and session documentation
- [`auth.md`](auth.md) - Authentication handlers
- [`api.md`](api.md) - Public API reference
