# Authentication Module Documentation

## Overview

The [`auth.py`](../src/arequest/auth.py) module provides authentication handlers for arequest, supporting common HTTP authentication schemes:

- [`AuthBase`](../src/arequest/auth.py:10) - Base class for authentication handlers
- [`BasicAuth`](../src/arequest/auth.py:22) - HTTP Basic Authentication
- [`BearerAuth`](../src/arequest/auth.py:46) - Bearer Token Authentication

These authentication handlers can be used with [`Session`](client.md#session) instances or individual requests to automatically add authentication headers.

---

## Classes

### AuthBase

Abstract base class for authentication handlers. All authentication implementations should inherit from this class.

#### Methods

##### [`apply(request)`](../src/arequest/auth.py:13)

Apply authentication to a request object.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `request` | `Any` | Request object with a `headers` attribute |

**Raises:** `NotImplementedError` - Must be implemented by subclasses

**Example:**

```python
from arequest.auth import AuthBase

class CustomAuth(AuthBase):
    def __init__(self, token):
        self.token = token
    
    def apply(self, request):
        request.headers['X-Custom-Auth'] = self.token
```

---

### BasicAuth

Implements HTTP Basic Authentication as specified in [RFC 7617](https://tools.ietf.org/html/rfc7617).

Basic Authentication encodes credentials using Base64 and adds them to the `Authorization` header in the format: `Basic <base64-encoded-credentials>`.

#### Constructor

```python
BasicAuth(username: str, password: str)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | `str` | Username for authentication |
| `password` | `str` | Password for authentication |

#### Methods

##### [`apply(request)`](../src/arequest/auth.py:35)

Apply Basic Authentication to the request.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `request` | `Any` | Request object with a `headers` attribute |

**Behavior:**
- Combines username and password in format `username:password`
- Encodes credentials using Base64
- Sets `Authorization` header to `Basic <base64-encoded-credentials>`

#### Example Usage

**With Session:**

```python
import asyncio
import arequest

async def main():
    # Create session with Basic Authentication
    auth = arequest.BasicAuth('myuser', 'mypassword')
    
    async with arequest.Session(auth=auth) as session:
        response = await session.get('https://httpbin.org/basic-auth/myuser/mypassword')
        print(f"Status: {response.status_code}")
        print(f"Authenticated: {response.json()['authenticated']}")

asyncio.run(main())
```

**With Individual Request:**

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        auth = arequest.BasicAuth('myuser', 'mypassword')
        response = await session.get(
            'https://httpbin.org/basic-auth/myuser/mypassword',
            auth=auth
        )
        print(f"Status: {response.status_code}")

asyncio.run(main())
```

**Manual Implementation:**

```python
import asyncio
import arequest
from arequest.auth import BasicAuth

async def main():
    auth = BasicAuth('admin', 'secret123')
    
    # Create a mock request object
    class MockRequest:
        headers = {}
    
    request = MockRequest()
    auth.apply(request)
    
    print(f"Authorization header: {request.headers['Authorization']}")
    # Output: Authorization header: Basic YWRtaW46c2VjcmV0MTIz

asyncio.run(main())
```

---

### BearerAuth

Implements Bearer Token Authentication as specified in [RFC 6750](https://tools.ietf.org/html/rfc6750).

Bearer Authentication is commonly used with OAuth 2.0 and adds the token to the `Authorization` header in the format: `Bearer <token>`.

#### Constructor

```python
BearerAuth(token: str)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | `str` | Bearer token string |

#### Methods

##### [`apply(request)`](../src/arequest/auth.py:57)

Apply Bearer Authentication to the request.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `request` | `Any` | Request object with a `headers` attribute |

**Behavior:**
- Sets `Authorization` header to `Bearer <token>`

#### Example Usage

**With Session:**

```python
import asyncio
import arequest

async def main():
    # Create session with Bearer Authentication
    auth = arequest.BearerAuth('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...')
    
    async with arequest.Session(auth=auth) as session:
        response = await session.get('https://api.example.com/protected')
        print(f"Status: {response.status_code}")
        print(response.json())

asyncio.run(main())
```

**With Individual Request:**

```python
import asyncio
import arequest

async def main():
    async with arequest.Session() as session:
        # Different tokens for different requests
        token1 = 'token1'
        token2 = 'token2'
        
        response1 = await session.get(
            'https://api.example.com/resource1',
            auth=arequest.BearerAuth(token1)
        )
        
        response2 = await session.get(
            'https://api.example.com/resource2',
            auth=arequest.BearerAuth(token2)
        )
        
        print(f"Response 1: {response1.status_code}")
        print(f"Response 2: {response2.status_code}")

asyncio.run(main())
```

**OAuth 2.0 Flow Example:**

```python
import asyncio
import arequest

async def get_access_token(client_id, client_secret):
    """Obtain OAuth 2.0 access token"""
    async with arequest.Session() as session:
        response = await session.post(
            'https://oauth.example.com/token',
            data={
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret
            }
        )
        return response.json()['access_token']

async def main():
    # Get access token
    token = await get_access_token('my_client_id', 'my_client_secret')
    
    # Use token for authenticated requests
    auth = arequest.BearerAuth(token)
    
    async with arequest.Session(auth=auth) as session:
        response = await session.get('https://api.example.com/user/profile')
        print(response.json())

asyncio.run(main())
```

---

## Creating Custom Authentication

You can create custom authentication handlers by extending [`AuthBase`](../src/arequest/auth.py:10).

### Example: API Key Authentication

```python
import arequest
from arequest.auth import AuthBase

class APIKeyAuth(AuthBase):
    """API Key authentication via custom header."""
    
    def __init__(self, api_key: str, header_name: str = 'X-API-Key'):
        self.api_key = api_key
        self.header_name = header_name
    
    def apply(self, request):
        request.headers[self.header_name] = self.api_key

# Usage
async def main():
    auth = APIKeyAuth('my-secret-api-key', 'X-API-Key')
    
    async with arequest.Session(auth=auth) as session:
        response = await session.get('https://api.example.com/data')
        print(response.json())

asyncio.run(main())
```

### Example: HMAC Authentication

```python
import arequest
from arequest.auth import AuthBase
import hmac
import hashlib
import base64

class HMACAuth(AuthBase):
    """HMAC-based authentication."""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
    
    def apply(self, request):
        # Generate signature (simplified example)
        timestamp = str(int(time.time()))
        message = f"{timestamp}{request.headers.get('Content-Type', '')}"
        
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        
        encoded_signature = base64.b64encode(signature).decode()
        
        request.headers['X-API-Key'] = self.api_key
        request.headers['X-Timestamp'] = timestamp
        request.headers['X-Signature'] = encoded_signature

# Usage
async def main():
    auth = HMACAuth('my_api_key', 'my_secret_key')
    
    async with arequest.Session(auth=auth) as session:
        response = await session.post(
            'https://api.example.com/data',
            json={'key': 'value'}
        )
        print(response.json())

asyncio.run(main())
```

### Example: JWT Authentication with Refresh

```python
import arequest
from arequest.auth import AuthBase

class JWTAuth(AuthBase):
    """JWT authentication with automatic token refresh."""
    
    def __init__(self, access_token: str, refresh_token: str = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._session = None
    
    async def refresh_access_token(self):
        """Refresh the access token using refresh token."""
        if not self.refresh_token:
            raise ValueError("No refresh token available")
        
        async with arequest.Session() as session:
            response = await session.post(
                'https://auth.example.com/refresh',
                json={'refresh_token': self.refresh_token}
            )
            data = response.json()
            self.access_token = data['access_token']
    
    def apply(self, request):
        request.headers['Authorization'] = f'Bearer {self.access_token}'
    
    async def make_request(self, method: str, url: str, **kwargs):
        """Make request with automatic token refresh on 401."""
        if not self._session:
            self._session = arequest.Session(auth=self)
        
        async with self._session:
            response = await self._session.request(method, url, **kwargs)
            
            # Refresh token on 401 Unauthorized
            if response.status_code == 401:
                await self.refresh_access_token()
                response = await self._session.request(method, url, **kwargs)
            
            return response

# Usage
async def main():
    auth = JWTAuth(
        access_token='initial_access_token',
        refresh_token='initial_refresh_token'
    )
    
    # Use the custom make_request method
    response = await auth.make_request('GET', 'https://api.example.com/data')
    print(response.json())

asyncio.run(main())
```

---

## Best Practices

### 1. Store Credentials Securely

Never hardcode credentials in your code:

```python
# ❌ Bad
auth = BasicAuth('admin', 'password123')

# ✅ Good
import os
auth = BasicAuth(
    os.getenv('API_USERNAME'),
    os.getenv('API_PASSWORD')
)
```

### 2. Use Environment Variables or Configuration Files

```python
import os
from dotenv import load_dotenv

load_dotenv()

auth = BasicAuth(
    username=os.getenv('API_USERNAME'),
    password=os.getenv('API_PASSWORD')
)
```

### 3. Token Management for Bearer Auth

For Bearer tokens that expire:

```python
class TokenManager:
    def __init__(self):
        self.token = None
        self.expires_at = None
    
    async def get_token(self):
        if not self.token or self.is_expired():
            self.token = await self.fetch_new_token()
        return self.token
    
    def is_expired(self):
        return self.expires_at and time.time() > self.expires_at
```

### 4. Session vs Request-Level Auth

Use session-level authentication when all requests use the same credentials:

```python
# ✅ Good - Same auth for all requests
async with arequest.Session(auth=auth) as session:
    await session.get('https://api.example.com/resource1')
    await session.get('https://api.example.com/resource2')
```

Use request-level authentication when credentials vary:

```python
# ✅ Good - Different auth per request
async with arequest.Session() as session:
    await session.get('https://api.example.com/resource1', auth=auth1)
    await session.get('https://api.example.com/resource2', auth=auth2)
```

### 5. Error Handling

Always handle authentication failures:

```python
async def main():
    auth = BasicAuth('user', 'pass')
    
    async with arequest.Session(auth=auth) as session:
        try:
            response = await session.get('https://api.example.com/data')
            response.raise_for_status()
        except arequest.ClientError as e:
            if e.status_code == 401:
                print("Authentication failed - check credentials")
            else:
                print(f"Client error: {e.status_code}")

asyncio.run(main())
```

---

## Security Considerations

### Basic Authentication

- **Transmits credentials in plaintext** (Base64 is encoding, not encryption)
- Always use HTTPS to encrypt the connection
- Consider using more secure alternatives for production systems

### Bearer Authentication

- **Token must be kept secret** - anyone with the token can access the API
- Use short-lived tokens with refresh mechanisms
- Implement token revocation if possible
- Store tokens securely (e.g., encrypted at rest)

### General Security

1. **Never log authentication headers** or credentials
2. **Use HTTPS** for all authenticated requests
3. **Implement rate limiting** to prevent brute force attacks
4. **Rotate credentials** regularly
5. **Use strong passwords** for Basic Auth

---

## Troubleshooting

### 401 Unauthorized

**Possible causes:**
- Incorrect username/password for Basic Auth
- Expired or invalid token for Bearer Auth
- Token has insufficient permissions

**Solution:**
```python
try:
    response = await session.get('https://api.example.com/data')
    response.raise_for_status()
except arequest.ClientError as e:
    if e.status_code == 401:
        print("Authentication failed. Check your credentials.")
```

### 403 Forbidden

**Possible causes:**
- Authenticated but insufficient permissions
- Token has expired

**Solution:**
```python
try:
    response = await session.get('https://api.example.com/admin/data')
    response.raise_for_status()
except arequest.ClientError as e:
    if e.status_code == 403:
        print("Access denied. Check your permissions.")
```

---

## See Also

- [`client.md`](client.md) - HTTP client and session documentation
- [`parser.md`](parser.md) - HTTP parsing implementation
- [`api.md`](api.md) - Public API reference
