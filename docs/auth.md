# Authentication

arequest supports HTTP Basic auth, Bearer tokens and fully custom schemes.
Auth can be set per request or session-wide via the `auth` parameter.

## Basic Authentication

```python
import asyncio
import arequest

async def main():
    # Tuple shorthand (requests-style)
    r = await arequest.get(
        "https://httpbin.org/basic-auth/user/pass",
        auth=("user", "pass"),
    )

    # Or the explicit class
    auth = arequest.BasicAuth("user", "pass")
    async with arequest.Session(auth=auth) as s:
        r = await s.get("https://httpbin.org/basic-auth/user/pass")
        print(r.json())   # {'authenticated': True, 'user': 'user'}

asyncio.run(main())
```

## Bearer Tokens

```python
async def main():
    auth = arequest.BearerAuth("your-token")
    r = await arequest.get("https://httpbin.org/bearer", auth=auth)
    print(r.json())       # {'authenticated': True, 'token': 'your-token'}

asyncio.run(main())
```

## Session-Wide Auth

```python
async with arequest.Session(auth=BasicAuth("user", "pass")) as s:
    # every request carries the Authorization header
    await s.get("https://api.example.com/private")
```

Auth headers are dropped automatically on cross-origin redirect hops.

## Custom Authentication

Subclass `arequest.AuthBase` and implement `apply(request)`, which mutates and
returns the `PreparedRequest`. Both sync and `async` implementations work.

```python
import asyncio
import arequest
from arequest.auth import AuthBase

class APIKeyAuth(AuthBase):
    """Static API key header."""

    def __init__(self, api_key: str, header: str = "X-API-Key"):
        self.api_key = api_key
        self.header = header

    def apply(self, request):
        request.headers[self.header] = self.api_key
        return request


class TokenRefreshAuth(AuthBase):
    """Fetches a token lazily before each request."""

    def __init__(self, token_url: str, credentials: dict):
        self.token_url = token_url
        self.credentials = credentials
        self._token = None

    async def apply(self, request):
        if self._token is None:
            r = await arequest.post(self.token_url, json=self.credentials)
            self._token = r.json()["access_token"]
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request


async def main():
    async with arequest.Session(auth=APIKeyAuth("secret-key")) as s:
        r = await s.get("https://httpbin.org/headers")
        print(r.status_code)

asyncio.run(main())
```

A plain callable `(request) -> request` (or coroutine function) is also
accepted as `auth`.

## Auth vs. Impersonation Note

When impersonating a browser, your `Authorization`/`Cookie` headers are merged
on top of the browser's default header set - explicit headers always win.
