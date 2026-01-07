"""arequest - High-performance async HTTP client with a requests-like API.

Designed for low overhead and a familiar developer experience.

Example:
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
            import asyncio
            tasks = [session.get(f'https://httpbin.org/get?i={i}') for i in range(10)]
            responses = await asyncio.gather(*tasks)
    
    asyncio.run(main())
"""

__version__ = "0.2.0"

# Import main API
from .client import (
    # Core classes
    Session,
    Response,
    # Convenience functions
    request,
    get,
    post,
    put,
    delete,
    patch,
    head,
    options,
    # Exceptions
    ClientError,
    ServerError,
    TimeoutError,
)

# Import auth classes
from .auth import (
    AuthBase,
    BasicAuth,
    BearerAuth,
)

__all__ = [
    # Version
    "__version__",
    # Core classes
    "Session",
    "Response",
    # Convenience functions
    "request",
    "get",
    "post", 
    "put",
    "delete",
    "patch",
    "head",
    "options",
    # Exceptions
    "ClientError",
    "ServerError",
    "TimeoutError",
    # Auth
    "AuthBase",
    "BasicAuth",
    "BearerAuth",
]
