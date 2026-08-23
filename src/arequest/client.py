"""Async HTTP client with real browser fingerprints and a requests-like API.

``arequest`` pairs a familiar ``requests``-style interface with curl-impersonate
powered browser impersonation. Every request can present a byte-exact browser
fingerprint on the wire: TLS ClientHello (JA3/JA4), HTTP/2 settings (Akamai),
and the full browser header set in correct order.

Example:
    import asyncio
    import arequest

    async def main():
        # One-off request with Chrome's exact TLS/HTTP/2 fingerprint
        r = await arequest.get("https://tls.peet.ws/api/all", impersonate="chrome")
        print(r.json()["tls"]["ja4"])

        # Session for connection reuse across many requests
        async with arequest.Session(impersonate="chrome") as s:
            r = await s.get("https://httpbin.org/get")
            print(r.status_code)

    asyncio.run(main())
"""

import asyncio
import inspect
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Callable, Optional, Union
from urllib.parse import urljoin, urlsplit

from curl_cffi.requests import Headers

from .exceptions import (
    ClientError,
    ConnectionError,
    HTTPError,
    ImpersonationError,
    InvalidURL,
    ProxyError,
    RequestError,
    ServerError,
    SSLError,
    StreamError,
    TimeoutError,
    TooManyRedirects,
    TransportError,
    translate_exception,
)
from .limits import AsyncRateLimiter
from .models import PreparedRequest, Response, Timeout, normalize_timeout
from .profiles import available_profiles, resolve_impersonate
from .retry import RetryPolicy
from .transport import CurlTransport, create_cookie_jar, normalize_http_version

_UNSET = object()


def _merge_params(base: Any, override: Any) -> Any:
    if base is None:
        return override
    if override is None:
        return base
    if isinstance(base, Mapping) and isinstance(override, Mapping):
        return {**base, **override}
    base_items = list(base.items()) if isinstance(base, Mapping) else list(base)
    override_items = list(override.items()) if isinstance(override, Mapping) else list(override)
    return base_items + override_items


def _body_is_replayable(data: Any, files: Any, multipart: Any) -> bool:
    if multipart is not None:
        return False
    if files:
        values = files.values() if isinstance(files, Mapping) else files
        for value in values:
            candidate = value[1] if isinstance(value, tuple) and len(value) > 1 else value
            if hasattr(candidate, "read"):
                return False
    return data is None or isinstance(data, (bytes, bytearray, str, Mapping, list, tuple))


def _hook_list(value: Any) -> tuple[Callable[..., Any], ...]:
    if value is None:
        return ()
    if callable(value):
        return (value,)
    return tuple(value)


async def _call_hook(hook: Callable[..., Any], value: Any) -> Any:
    result = hook(value)
    if inspect.isawaitable(result):
        result = await result
    return value if result is None else result


def _normalize_proxy_configuration(proxies: Any, proxy: Optional[str]) -> tuple[Any, Optional[str]]:
    if isinstance(proxies, str):
        if proxy is not None:
            raise TypeError("cannot set both proxies as a string and proxy")
        return {}, proxies
    return dict(proxies or {}), proxy


class Session:
    """Async HTTP session with connection pooling and browser impersonation.

    Mirrors ``requests.Session`` semantics, but every method is ``await``-able.
    The session keeps cookies, headers, auth, proxy settings, connection pools,
    retry policy and rate limits consistent across requests.

    Args:
        headers: Default headers merged into every request.
        timeout: Default timeout in seconds, a ``(connect, read)`` tuple, or a
            :class:`~arequest.models.Timeout`.
        connector_limit: Maximum number of concurrent connections.
        connector_limit_per_host: Maximum concurrent connections per host
            (``0`` means unlimited).
        auth: Default auth handler or ``(username, password)`` tuple.
        verify: Verify TLS certificates.
        impersonate: Browser profile to impersonate (e.g. ``"chrome"``,
            ``"chrome131"``). Use :func:`available_profiles` to list options,
            or ``None`` to send plain requests.
        retries: Number of automatic retries or a
            :class:`~arequest.retry.RetryPolicy`.

    Example:
        async with arequest.Session(impersonate="chrome", retries=3) as s:
            r = await s.get("https://example.com")
            r.raise_for_status()
    """

    def __init__(
        self,
        headers: Any = None,
        timeout: Any = 30.0,
        connector_limit: int = 100,
        connector_limit_per_host: int = 0,
        auth: Any = None,
        verify: bool = True,
        *,
        cookies: Any = None,
        proxies: Any = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        base_url: Optional[str] = None,
        params: Any = None,
        trust_env: bool = True,
        allow_redirects: bool = True,
        max_redirects: int = 30,
        impersonate: Any = "chrome",
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
        extra_fp: Any = None,
        default_headers: bool = True,
        default_encoding: Any = "utf-8",
        http_version: Any = "auto",
        retries: Union[int, RetryPolicy] = 0,
        backoff: Optional[float] = None,
        stream: bool = False,
        cert: Any = None,
        interface: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        rate_limit: Optional[float] = None,
        rate_limit_per_host: Optional[float] = None,
        rate_limit_burst: int = 1,
        hooks: Optional[Mapping[str, Any]] = None,
        debug: bool = False,
        curl_options: Optional[Mapping[Any, Any]] = None,
        curl_infos: Any = None,
        transport: Any = None,
    ) -> None:
        if connector_limit < 0 or connector_limit_per_host < 0:
            raise ValueError("connector limits cannot be negative")
        if max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")
        if base_url is not None:
            parts = urlsplit(base_url)
            if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
                raise InvalidURL(f"invalid base URL: {base_url!r}")
        self._headers = Headers(headers)
        self._timeout = normalize_timeout(timeout)
        self._closed = False
        self._connector_limit = connector_limit
        self._max_per_host = connector_limit_per_host
        self._global_semaphore = asyncio.Semaphore(connector_limit) if connector_limit else None
        self._host_semaphores: dict[tuple[str, str, int], asyncio.Semaphore] = {}
        self.auth = auth
        self.verify = bool(verify)
        self.proxies, self.proxy = _normalize_proxy_configuration(proxies, proxy)
        self.proxy_auth = proxy_auth
        self.base_url = base_url
        self.params = params
        self.stream = bool(stream)
        self.cert = cert
        self.interface = interface
        self.max_redirects = max_redirects
        self.allow_redirects = bool(allow_redirects)
        self.trust_env = bool(trust_env)
        self.impersonate = resolve_impersonate(impersonate)
        self.ja3 = ja3
        self.akamai = akamai
        self.extra_fp = extra_fp
        self.default_headers = bool(default_headers)
        self.default_encoding = default_encoding
        self.http_version = normalize_http_version(http_version)
        self.accept_encoding = accept_encoding
        self.retry_policy = RetryPolicy.from_value(retries, backoff_factor=backoff)
        self.hooks = dict(hooks or {})
        self._rate_limiter = (
            AsyncRateLimiter(rate_limit, rate_limit_burst) if rate_limit is not None else None
        )
        self._per_host_rate = rate_limit_per_host
        self._rate_limit_burst = rate_limit_burst
        self._host_limiters: dict[tuple[str, str, int], AsyncRateLimiter] = {}
        cookie_jar = create_cookie_jar(cookies)
        self._transport = transport or CurlTransport(
            max_clients=max(1, connector_limit or 100),
            cookies=cookie_jar,
            trust_env=trust_env,
            debug=debug,
            curl_options=curl_options,
            curl_infos=curl_infos,
        )
        self._cookies = getattr(self._transport, "cookies", cookie_jar)

    @property
    def headers(self) -> Headers:
        return self._headers

    @headers.setter
    def headers(self, value: Any) -> None:
        self._headers = Headers(value)

    @property
    def cookies(self) -> Any:
        return self._cookies

    @cookies.setter
    def cookies(self, value: Any) -> None:
        jar = create_cookie_jar(value)
        self._cookies = jar
        raw_session = getattr(self._transport, "raw_session", None)
        if raw_session is not None:
            raw_session.cookies = jar

    @property
    def timeout(self) -> Any:
        return self._timeout

    @timeout.setter
    def timeout(self, value: Any) -> None:
        self._timeout = normalize_timeout(value)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def transport_name(self) -> str:
        return str(getattr(self._transport, "name", self._transport.__class__.__name__))

    async def _run_hooks(self, name: str, value: Any) -> Any:
        for hook in _hook_list(self.hooks.get(name)):
            value = await _call_hook(hook, value)
        return value

    async def _wait_for_rate_limit(self, url: str) -> None:
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        if self._per_host_rate is not None:
            key = self._origin_key(url)
            limiter = self._host_limiters.get(key)
            if limiter is None:
                limiter = AsyncRateLimiter(self._per_host_rate, self._rate_limit_burst)
                self._host_limiters[key] = limiter
            await limiter.acquire()

    @staticmethod
    def _origin_key(url: str) -> tuple[str, str, int]:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        return parts.scheme.lower(), (parts.hostname or "").lower(), port

    async def _acquire_slot(self, url: str) -> Callable[[], None]:
        acquired_global = False
        host_semaphore: Optional[asyncio.Semaphore] = None
        if self._global_semaphore is not None:
            await self._global_semaphore.acquire()
            acquired_global = True
        try:
            if self._max_per_host:
                key = self._origin_key(url)
                host_semaphore = self._host_semaphores.get(key)
                if host_semaphore is None:
                    host_semaphore = asyncio.Semaphore(self._max_per_host)
                    self._host_semaphores[key] = host_semaphore
                await host_semaphore.acquire()
        except BaseException:
            if acquired_global and self._global_semaphore is not None:
                self._global_semaphore.release()
            raise

        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            if host_semaphore is not None:
                host_semaphore.release()
            if acquired_global and self._global_semaphore is not None:
                self._global_semaphore.release()

        return release

    def _resolve_url(self, url: str) -> str:
        if not isinstance(url, str) or not url.strip():
            raise InvalidURL("url must be a non-empty string")
        resolved = urljoin(self.base_url.rstrip("/") + "/", url) if self.base_url else url
        parts = urlsplit(resolved)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            raise InvalidURL(f"invalid HTTP URL: {resolved!r}")
        return resolved

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Any = None,
        params: Any = None,
        data: Any = None,
        json: Any = None,
        files: Any = None,
        timeout: Any = _UNSET,
        verify: Optional[bool] = None,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        auth: Any = None,
        cookies: Any = None,
        proxies: Any = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        impersonate: Any = _UNSET,
        ja3: Any = _UNSET,
        akamai: Any = _UNSET,
        extra_fp: Any = _UNSET,
        default_headers: Optional[bool] = None,
        default_encoding: Any = None,
        http_version: Any = _UNSET,
        stream: Optional[bool] = None,
        retries: Any = _UNSET,
        backoff: Optional[float] = None,
        hooks: Optional[Mapping[str, Any]] = None,
        referer: Optional[str] = None,
        accept_encoding: Any = _UNSET,
        content_callback: Optional[Callable[..., Any]] = None,
        quote: Union[str, bool] = "",
        interface: Optional[str] = None,
        cert: Any = None,
        max_recv_speed: int = 0,
        multipart: Any = None,
        discard_cookies: bool = False,
    ) -> Response:
        if self._closed:
            raise RuntimeError("Session is closed")
        if not isinstance(method, str) or not method.strip() or any(
            char.isspace() for char in method
        ):
            raise ValueError("method must be a non-empty HTTP token")

        request_method = method.upper()
        request_url = self._resolve_url(url)
        request_headers = self._headers.copy()
        if headers is not None:
            request_headers.update(headers)
        prepared = PreparedRequest(request_method, request_url, request_headers)

        request_auth = self.auth if auth is None else auth
        curl_auth = None
        if request_auth is not None:
            if isinstance(request_auth, tuple) and len(request_auth) == 2:
                curl_auth = request_auth
            elif hasattr(request_auth, "apply"):
                result = request_auth.apply(prepared)
                if inspect.isawaitable(result):
                    await result
            elif callable(request_auth):
                result = request_auth(prepared)
                if inspect.isawaitable(result):
                    await result
            else:
                raise TypeError("auth must be a (username, password) tuple or an auth handler")

        prepared = await self._run_hooks("request", prepared)
        for hook in _hook_list((hooks or {}).get("request")):
            prepared = await _call_hook(hook, prepared)
        if not isinstance(prepared, PreparedRequest):
            raise TypeError("request hooks must return PreparedRequest or None")

        request_method = prepared.method.upper()
        request_url = self._resolve_url(prepared.url)
        request_headers = prepared.headers
        request_timeout = self._timeout if timeout is _UNSET else normalize_timeout(timeout)
        request_verify = self.verify if verify is None else bool(verify)
        follow_redirects = self.allow_redirects if allow_redirects is None else allow_redirects
        redirect_limit = self.max_redirects if max_redirects is None else max_redirects
        if redirect_limit < 0:
            raise ValueError("max_redirects cannot be negative")
        request_stream = self.stream if stream is None else bool(stream)
        request_impersonate = (
            self.impersonate
            if impersonate is _UNSET
            else resolve_impersonate(impersonate)
        )
        request_ja3 = self.ja3 if ja3 is _UNSET else ja3
        request_akamai = self.akamai if akamai is _UNSET else akamai
        request_extra_fp = self.extra_fp if extra_fp is _UNSET else extra_fp
        request_http_version = (
            self.http_version
            if http_version is _UNSET
            else normalize_http_version(http_version)
        )
        if request_http_version is None and urlsplit(request_url).scheme.lower() == "http":
            request_http_version = "v1"
        request_default_headers = (
            self.default_headers if default_headers is None else bool(default_headers)
        )
        request_default_encoding = (
            self.default_encoding if default_encoding is None else default_encoding
        )
        request_accept_encoding = (
            self.accept_encoding if accept_encoding is _UNSET else accept_encoding
        )
        request_proxies = self.proxies if proxies is None else proxies
        request_proxy = self.proxy if proxy is None else proxy
        if isinstance(request_proxies, str):
            if request_proxy is not None:
                raise TypeError("cannot set both proxies as a string and proxy")
            request_proxy = request_proxies
            request_proxies = {}
        request_proxy_auth = self.proxy_auth if proxy_auth is None else proxy_auth
        request_interface = self.interface if interface is None else interface
        request_cert = self.cert if cert is None else cert
        request_params = _merge_params(self.params, params)
        policy = (
            RetryPolicy.from_value(self.retry_policy, backoff_factor=backoff)
            if retries is _UNSET
            else RetryPolicy.from_value(retries, backoff_factor=backoff)
        )
        replayable = _body_is_replayable(data, files, multipart)
        retries_used = 0

        while True:
            prepared.attempt = retries_used + 1
            await self._wait_for_rate_limit(request_url)
            release = await self._acquire_slot(request_url)
            try:
                raw_response = await self._transport.request(
                    request_method,
                    request_url,
                    params=request_params,
                    data=data,
                    json=json,
                    headers=request_headers,
                    cookies=cookies,
                    files=files,
                    auth=curl_auth,
                    timeout=request_timeout,
                    allow_redirects=follow_redirects,
                    max_redirects=redirect_limit,
                    proxies=request_proxies,
                    proxy=request_proxy,
                    proxy_auth=request_proxy_auth,
                    verify=request_verify,
                    referer=referer,
                    accept_encoding=request_accept_encoding,
                    content_callback=content_callback,
                    impersonate=request_impersonate,
                    ja3=request_ja3,
                    akamai=request_akamai,
                    extra_fp=request_extra_fp,
                    default_headers=request_default_headers,
                    default_encoding=request_default_encoding,
                    quote=quote,
                    http_version=request_http_version,
                    interface=request_interface,
                    cert=request_cert,
                    stream=request_stream,
                    max_recv_speed=max_recv_speed,
                    multipart=multipart,
                    discard_cookies=discard_cookies,
                )
            except asyncio.CancelledError:
                release()
                raise
            except Exception as exc:
                release()
                error = translate_exception(exc, request_url)
                if replayable and policy.should_retry(
                    request_method,
                    retries_used,
                    error=error,
                ):
                    retries_used += 1
                    delay = policy.get_delay(retries_used)
                    if delay:
                        await asyncio.sleep(delay)
                    continue
                if error is exc:
                    raise
                raise error from exc

            is_streaming = getattr(raw_response, "queue", None) is not None
            raw_request = getattr(raw_response, "request", None)
            response_request = PreparedRequest(
                method=str(getattr(raw_request, "method", prepared.method)),
                url=str(getattr(raw_request, "url", prepared.url)),
                headers=getattr(raw_request, "headers", prepared.headers),
                attempt=prepared.attempt,
            )
            response = Response(
                raw_response,
                request=response_request,
                release=release if is_streaming else None,
                attempts=retries_used + 1,
            )
            if not is_streaming:
                release()

            original_response = response
            try:
                response = await self._run_hooks("response", response)
                for hook in _hook_list((hooks or {}).get("response")):
                    response = await _call_hook(hook, response)
                if not isinstance(response, Response):
                    raise TypeError("response hooks must return Response or None")
                if response is not original_response:
                    await original_response.aclose()
            except BaseException:
                await original_response.aclose()
                raise

            if replayable and policy.should_retry(
                request_method,
                retries_used,
                response=response,
            ):
                retries_used += 1
                delay = policy.get_delay(retries_used, response)
                await response.aclose()
                if delay:
                    await asyncio.sleep(delay)
                continue
            response.attempts = retries_used + 1
            return response

    async def get(self, url: str, **kwargs: Any) -> Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Response:
        return await self.request("DELETE", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> Response:
        return await self.request("PATCH", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> Response:
        return await self.request("HEAD", url, **kwargs)

    async def options(self, url: str, **kwargs: Any) -> Response:
        return await self.request("OPTIONS", url, **kwargs)

    async def gather(
        self,
        *requests: Any,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> Sequence[Any]:
        pending = []
        for item in requests:
            if isinstance(item, str):
                pending.append(self.get(item, **kwargs))
            elif isinstance(item, Mapping):
                spec = dict(item)
                item_method = spec.pop("method", "GET")
                item_url = spec.pop("url")
                pending.append(self.request(item_method, item_url, **{**kwargs, **spec}))
            elif len(item) == 2:
                pending.append(self.request(item[0], item[1], **kwargs))
            elif len(item) == 3:
                pending.append(self.request(item[0], item[1], **{**kwargs, **item[2]}))
            else:
                raise ValueError("request specs must contain (method, url[, kwargs])")
        return await asyncio.gather(*pending, return_exceptions=return_exceptions)

    async def bulk_get(
        self,
        urls: Iterable[str],
        *,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> Sequence[Any]:
        return await asyncio.gather(
            *(self.get(url, **kwargs) for url in urls),
            return_exceptions=return_exceptions,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._transport.close()

    async def __aenter__(self) -> "Session":
        if self._closed:
            raise RuntimeError("Session is closed")
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


_sessions: dict[asyncio.AbstractEventLoop, Session] = {}


def _get_session() -> Session:
    loop = asyncio.get_running_loop()
    session = _sessions.get(loop)
    if session is None or session.closed:
        session = Session()
        _sessions[loop] = session
    return session


async def aclose() -> None:
    loop = asyncio.get_running_loop()
    session = _sessions.pop(loop, None)
    if session is not None:
        await session.close()


async def request(method: str, url: str, **kwargs: Any) -> Response:
    return await _get_session().request(method, url, **kwargs)


async def get(url: str, **kwargs: Any) -> Response:
    return await request("GET", url, **kwargs)


async def post(url: str, **kwargs: Any) -> Response:
    return await request("POST", url, **kwargs)


async def put(url: str, **kwargs: Any) -> Response:
    return await request("PUT", url, **kwargs)


async def delete(url: str, **kwargs: Any) -> Response:
    return await request("DELETE", url, **kwargs)


async def patch(url: str, **kwargs: Any) -> Response:
    return await request("PATCH", url, **kwargs)


async def head(url: str, **kwargs: Any) -> Response:
    return await request("HEAD", url, **kwargs)


async def options(url: str, **kwargs: Any) -> Response:
    return await request("OPTIONS", url, **kwargs)


__all__ = [
    "ClientError",
    "ConnectionError",
    "HTTPError",
    "ImpersonationError",
    "InvalidURL",
    "PreparedRequest",
    "ProxyError",
    "RequestError",
    "Response",
    "RetryPolicy",
    "SSLError",
    "ServerError",
    "Session",
    "StreamError",
    "Timeout",
    "TimeoutError",
    "TooManyRedirects",
    "TransportError",
    "aclose",
    "available_profiles",
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "request",
]
