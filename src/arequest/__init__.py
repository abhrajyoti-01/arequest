"""arequest - Fast async HTTP client with real browser fingerprints.

A ``requests``-style API on top of curl-impersonate: byte-exact TLS (JA3/JA4)
and HTTP/2 (Akamai) fingerprints, connection pooling, retries, rate limiting
and streaming responses.

Example:
    import asyncio
    import arequest

    async def main():
        response = await arequest.get('https://httpbin.org/get')
        print(response.json())

        async with arequest.Session(impersonate='chrome') as session:
            resp = await session.get('https://tls.peet.ws/api/all')
            print(resp.json()['tls']['ja4'])

    asyncio.run(main())
"""

__version__ = "2.3.0"

from .auth import AuthBase, BasicAuth, BearerAuth
from .client import (
    ClientError,
    ConnectionError,
    HTTPError,
    ImpersonationError,
    InvalidURL,
    PreparedRequest,
    ProxyError,
    RequestError,
    Response,
    RetryPolicy,
    ServerError,
    Session,
    SSLError,
    StreamError,
    Timeout,
    TimeoutError,
    TooManyRedirects,
    TransportError,
    WebSocket,
    aclose,
    available_profiles,
    delete,
    get,
    head,
    options,
    patch,
    post,
    put,
    request,
)
from .proxypool import ProxyPool

__all__ = [
    "__version__",
    "Session",
    "Response",
    "PreparedRequest",
    "Timeout",
    "RetryPolicy",
    "request",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "head",
    "options",
    "aclose",
    "available_profiles",
    "ProxyPool",
    "WebSocket",
    "AuthBase",
    "BasicAuth",
    "BearerAuth",
    "RequestError",
    "TransportError",
    "ConnectionError",
    "ProxyError",
    "SSLError",
    "HTTPError",
    "ClientError",
    "ServerError",
    "TimeoutError",
    "InvalidURL",
    "TooManyRedirects",
    "ImpersonationError",
    "StreamError",
]
