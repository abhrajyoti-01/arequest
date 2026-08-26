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
import json
import os
import random
import time
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import Any, Union
from urllib.parse import urljoin, urlsplit

from curl_cffi.requests import Headers, WebSocket

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
    contains_control_characters,
    strip_credentials,
    translate_exception,
)
from .limits import AsyncRateLimiter
from .models import PreparedRequest, Response, Timeout, normalize_timeout
from .profiles import available_profiles, resolve_impersonate
from .proxypool import ProxyPool
from .retry import RetryPolicy
from .transport import CurlTransport, create_cookie_jar, normalize_http_version

_UNSET = object()


def _noop() -> None:
    """No-op release used on the un-limited fast path."""


class _AsyncSocketHandle:
    """Thin wrapper adding ``async with`` support to impersonated sockets."""

    __slots__ = ("_socket",)

    def __init__(self, socket: Any) -> None:
        self._socket = socket

    @property
    def raw(self) -> Any:
        return self._socket

    async def __aenter__(self) -> Any:
        return self._socket

    async def __aexit__(self, *exc_info: Any) -> None:
        close = getattr(self._socket, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._socket, name)

    def __repr__(self) -> str:
        return f"<{_AsyncSocketHandle.__name__} {self._socket!r}>"


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
    return data is None or isinstance(data, bytes | bytearray | str | Mapping | list | tuple)


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


def _normalize_proxy_configuration(proxies: Any, proxy: str | None) -> tuple[Any, str | None]:
    if isinstance(proxies, str):
        if proxy is not None:
            raise TypeError("cannot set both proxies as a string and proxy")
        return {}, proxies
    return dict(proxies or {}), proxy


# User-Agent strings that match the shipped impersonation profiles. Kept in
# sync with the profile families shipped by curl_cffi's BrowserTypeLiteral.
_USER_AGENTS = {
    "chrome": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ),
    "firefox": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
        "Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:133.0) "
        "Gecko/20100101 Firefox/133.0",
    ),
    "safari": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.1.1 Safari/605.1.15",
    ),
    "edge": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.70",
    ),
}
_GENERIC_UA_POOL = tuple(ua for pool in _USER_AGENTS.values() for ua in pool)

# Common, real-world Accept-Language header values weighted toward English but
# reflecting typical browser diversity.
_ACCEPT_LANGUAGES = (
    "en-US,en;q=0.9",
    "en-US,en;q=0.9",
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.8",
    "en;q=0.9,en-US;q=0.8",
)


class _UserAgentRotator:
    """Rotates through a pool of User-Agent strings.

    ``source`` may be ``None`` (no rotation), ``"auto"`` (derive from the
    session's impersonate profile), a single UA string, or an iterable of UA
    strings.
    """

    __slots__ = ("_pool", "_index")

    def __init__(self, source: Any, impersonate: str | None) -> None:
        self._pool: tuple[str, ...] = ()
        self._index = 0
        if source is None or source is False:
            return
        if source is True or source == "auto":
            family = (impersonate or "chrome")
            for key, pool in _USER_AGENTS.items():
                if family.startswith(key):
                    self._pool = pool
                    return
            self._pool = _GENERIC_UA_POOL
            return
        if isinstance(source, str):
            self._pool = (source,)
            return
        pool = tuple(str(u) for u in source)
        if not pool:
            return
        self._pool = pool

    @property
    def enabled(self) -> bool:
        return len(self._pool) > 1

    def next(self) -> str | None:
        if not self._pool:
            return None
        if len(self._pool) == 1:
            return self._pool[0]
        ua = self._pool[self._index % len(self._pool)]
        self._index += 1
        return ua


def _normalize_think_time(value: Any) -> tuple[float, float] | None:
    if value is None or value is False:
        return None
    if isinstance(value, int | float):
        delay = float(value)
        if delay < 0:
            raise ValueError("think_time cannot be negative")
        return (delay, delay)
    if isinstance(value, tuple | list) and len(value) == 2:
        low, high = float(value[0]), float(value[1])
        if low < 0 or high < 0:
            raise ValueError("think_time values cannot be negative")
        if high < low:
            low, high = high, low
        return (low, high)
    raise TypeError("think_time must be a number, a (min, max) tuple, or None")


def _build_realistic_headers(impersonate: str | None, user_agent: str | None) -> dict[str, str]:
    """Build a coherent browser-like request header set.

    These complement (not replace) curl-impersonate's fingerprint headers,
    so they are only applied when the caller has not explicitly set them.
    """
    family = (impersonate or "chrome").lower()
    headers: dict[str, str] = {
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if family.startswith(("chrome", "edge")):
        brand = "Microsoft Edge" if family.startswith("edge") else "Google Chrome"
        version = (user_agent or "").split("Chrome/")[-1].split(".")[0] or "131"
        headers.update(
            {
                "Sec-CH-UA": (
                    f'"Chromium";v="{version}", "{brand}";v="{version}", '
                    f'"Not-A.Brand";v="99"'
                ),
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
            }
        )
    return headers


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
        rate_limit_jitter: Max extra random delay (seconds) added to rate-limit
            pacing to smooth bursts.
        realistic_headers: When ``True``, layer a coherent browser header set
            (Accept-Language, Sec-Fetch-*, Sec-CH-UA, ...) onto each request
            without overriding headers the caller explicitly set.
        user_agent_rotation: Rotate the User-Agent header: ``"auto"`` derives a
            pool from ``impersonate``; or pass a single UA string / iterable of
            UA strings. ``None`` disables rotation.
        think_time: Human-like pacing between requests: a number of seconds or
            a ``(min, max)`` tuple for a randomized delay.

    Example:
        async with arequest.Session(impersonate="chrome", retries=3) as s:
            r = await s.get("https://example.com")
            r.raise_for_status()
    """

    _STATE_VERSION = 1

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
        proxy: str | None = None,
        proxy_pool: Any = None,
        proxy_auth: tuple[str, str] | None = None,
        base_url: str | None = None,
        params: Any = None,
        trust_env: bool = True,
        allow_redirects: bool = True,
        max_redirects: int = 30,
        impersonate: Any = "chrome",
        ja3: str | None = None,
        akamai: str | None = None,
        extra_fp: Any = None,
        default_headers: bool = True,
        default_encoding: Any = "utf-8",
        http_version: Any = "auto",
        retries: int | RetryPolicy = 0,
        backoff: float | None = None,
        stream: bool = False,
        cert: Any = None,
        interface: str | None = None,
        accept_encoding: str | None = "gzip, deflate, br",
        rate_limit: float | None = None,
        rate_limit_per_host: float | None = None,
        rate_limit_burst: int = 1,
        rate_limit_jitter: float = 0.0,
        realistic_headers: bool = False,
        user_agent_rotation: Any = None,
        think_time: Any = None,
        hooks: Mapping[str, Any] | None = None,
        debug: bool = False,
        curl_options: Mapping[Any, Any] | None = None,
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
        if proxy_pool is None:
            self._proxy_pool: ProxyPool | None = None
        elif isinstance(proxy_pool, ProxyPool):
            self._proxy_pool = proxy_pool
        else:
            self._proxy_pool = ProxyPool(proxy_pool)
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
        if rate_limit_jitter < 0:
            raise ValueError("rate_limit_jitter cannot be negative")
        self._rate_limit_jitter = float(rate_limit_jitter)
        self._rate_limiter = (
            AsyncRateLimiter(rate_limit, rate_limit_burst, jitter=self._rate_limit_jitter)
            if rate_limit is not None
            else None
        )
        self._per_host_rate = rate_limit_per_host
        self._rate_limit_burst = rate_limit_burst
        self._host_limiters: dict[tuple[str, str, int], AsyncRateLimiter] = {}
        self._needs_limiting = bool(
            self._rate_limiter is not None
            or self._per_host_rate is not None
            or self._global_semaphore is not None
            or self._max_per_host
        )
        self.realistic_headers = bool(realistic_headers)
        self._user_agent_rotation_source = user_agent_rotation
        self.user_agent_rotation = _UserAgentRotator(user_agent_rotation, self.impersonate)
        self.think_time = _normalize_think_time(think_time)
        self._last_request_at: float | None = None
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

    @property
    def proxy_pool(self) -> ProxyPool | None:
        return self._proxy_pool

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
                limiter = AsyncRateLimiter(
                    self._per_host_rate,
                    self._rate_limit_burst,
                    jitter=self._rate_limit_jitter,
                )
                self._host_limiters[key] = limiter
            await limiter.acquire()

    @staticmethod
    def _origin_key(url: str) -> tuple[str, str, int]:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        return parts.scheme.lower(), (parts.hostname or "").lower(), port

    async def _acquire_slot(self, url: str) -> Callable[[], None]:
        acquired_global = False
        host_semaphore: asyncio.Semaphore | None = None
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

    async def _apply_think_time(self) -> None:
        low, high = self.think_time or (0.0, 0.0)
        delay = low if low == high else random.uniform(low, high)
        now = time.monotonic()
        last = self._last_request_at
        self._last_request_at = now + max(delay, 0.0)
        if last is None or delay <= 0:
            if delay > 0:
                await asyncio.sleep(delay)
            return
        wait = (last + delay) - now
        if wait > 0:
            await asyncio.sleep(wait)

    def _serialize_user_agent_rotation(self) -> Any:
        source = self._user_agent_rotation_source
        if source is None or isinstance(source, str | bool):
            return source
        try:
            return list(source)
        except TypeError:
            return None

    def _resolve_url(self, url: str) -> str:
        if not isinstance(url, str) or not url.strip():
            raise InvalidURL("url must be a non-empty string")
        if contains_control_characters(url):
            raise InvalidURL("url contains control characters")
        resolved = urljoin(self.base_url.rstrip("/") + "/", url) if self.base_url else url
        parts = urlsplit(resolved)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            raise InvalidURL(f"invalid HTTP URL: {strip_credentials(resolved)!r}")
        try:
            port = parts.port
        except ValueError as exc:
            raise InvalidURL(
                f"URL has an invalid port: {strip_credentials(resolved)!r}"
            ) from exc
        if port is not None and not (1 <= port <= 65535):
            raise InvalidURL(f"URL port out of range: {strip_credentials(resolved)!r}")
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
        verify: bool | None = None,
        allow_redirects: bool | None = None,
        max_redirects: int | None = None,
        auth: Any = None,
        cookies: Any = None,
        proxies: Any = None,
        proxy: str | None = None,
        proxy_auth: tuple[str, str] | None = None,
        impersonate: Any = _UNSET,
        ja3: Any = _UNSET,
        akamai: Any = _UNSET,
        extra_fp: Any = _UNSET,
        default_headers: bool | None = None,
        default_encoding: Any = None,
        http_version: Any = _UNSET,
        stream: bool | None = None,
        retries: Any = _UNSET,
        backoff: float | None = None,
        hooks: Mapping[str, Any] | None = None,
        referer: str | None = None,
        accept_encoding: Any = _UNSET,
        content_callback: Callable[..., Any] | None = None,
        quote: str | bool = "",
        interface: str | None = None,
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
        request_impersonate = (
            self.impersonate
            if impersonate is _UNSET
            else resolve_impersonate(impersonate)
        )

        # Layer in realistic browser headers / rotate UA without clobbering
        # headers the caller set.
        if self.realistic_headers or self.user_agent_rotation.enabled:
            rotation_ua = self.user_agent_rotation.next()
            merged_headers = Headers(request_headers)
            if rotation_ua is not None and self.user_agent_rotation.enabled:
                merged_headers["User-Agent"] = rotation_ua
            if self.realistic_headers:
                realistic = _build_realistic_headers(
                    request_impersonate or self.impersonate,
                    rotation_ua or merged_headers.get("User-Agent"),
                )
                for name, value in realistic.items():
                    if name not in merged_headers:
                        merged_headers[name] = value
            request_headers = merged_headers
        request_timeout = self._timeout if timeout is _UNSET else normalize_timeout(timeout)
        request_verify = self.verify if verify is None else bool(verify)
        follow_redirects = self.allow_redirects if allow_redirects is None else allow_redirects
        redirect_limit = self.max_redirects if max_redirects is None else max_redirects
        if redirect_limit < 0:
            raise ValueError("max_redirects cannot be negative")
        request_stream = self.stream if stream is None else bool(stream)
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

        if self.think_time is not None:
            await self._apply_think_time()

        needs_limiting = self._needs_limiting

        while True:
            prepared.attempt = retries_used + 1
            if needs_limiting:
                await self._wait_for_rate_limit(request_url)
                release = await self._acquire_slot(request_url)
            else:
                release = _noop
            pool_proxy: str | None = None
            attempt_proxy = request_proxy
            if self._proxy_pool is not None and attempt_proxy is None and not request_proxies:
                pool_proxy = self._proxy_pool.acquire()
                attempt_proxy = pool_proxy
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
                    proxy=attempt_proxy,
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
                if pool_proxy is not None and isinstance(error, ConnectionError):
                    self._proxy_pool.report_failure(pool_proxy)
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

            if pool_proxy is not None:
                self._proxy_pool.report_success(pool_proxy)
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

    async def iter_fetch(
        self,
        urls: Iterable[str],
        *,
        max_concurrency: int = 10,
        method: str = "GET",
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Fetch URLs concurrently with a concurrency cap.

        Yields each :class:`Response` as soon as it completes (completion
        order, not URL order). With ``return_exceptions=True`` failed requests
        are yielded as exception instances instead of aborting the iteration.

        Example:
            async for response in session.iter_fetch(urls, max_concurrency=20):
                print(response.status_code)
        """
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least one")
        url_queue: asyncio.Queue[Any] = asyncio.Queue()
        for url in urls:
            url_queue.put_nowait(url)
        result_queue: asyncio.Queue[Any] = asyncio.Queue()
        _sentinel = object()
        _error_marker = object()

        async def worker() -> None:
            while True:
                item = await url_queue.get()
                if item is _sentinel:
                    url_queue.task_done()
                    return
                try:
                    response = await self.request(method, item, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - surfaced to consumer
                    result_queue.put_nowait((_error_marker, exc))
                else:
                    result_queue.put_nowait((item, response))
                finally:
                    url_queue.task_done()

        workers = [
            asyncio.ensure_future(worker())
            for _ in range(min(max_concurrency, url_queue.qsize()) or 1)
        ]
        # Push sentinels so workers exit once the URL queue is drained.
        for _ in workers:
            url_queue.put_nowait(_sentinel)

        total = url_queue.qsize() - len(workers)  # URLs minus sentinels
        outstanding = total
        try:
            while outstanding > 0:
                kind, payload = await result_queue.get()
                outstanding -= 1
                if kind is _error_marker:
                    if not return_exceptions:
                        raise payload
                    yield payload
                else:
                    yield payload
        finally:
            while not url_queue.empty():
                try:
                    url_queue.get_nowait()
                    url_queue.task_done()
                except asyncio.QueueEmpty:
                    break
            for w in workers:
                if not w.done():
                    w.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)

    async def save(self, path: Union[str, "os.PathLike[str]"]) -> None:
        """Persist session state (cookies, headers, settings) to a JSON file.

        Auth handlers and hooks are not serialized. Proxy credentials are -
        protect the resulting file accordingly. The file is created with
        owner-only permissions (``0600``) where the platform supports it.
        """
        limiter_rate = self._rate_limiter.rate if self._rate_limiter is not None else None
        retry = self.retry_policy
        state = {
            "version": self._STATE_VERSION,
            "cookies": dict(self._cookies),
            "headers": dict(self._headers),
            "timeout": list(self._timeout) if isinstance(self._timeout, tuple) else self._timeout,
            "impersonate": self.impersonate,
            "verify": self.verify,
            "base_url": self.base_url,
            "proxies": self.proxies or None,
            "proxy": self.proxy,
            "proxy_auth": list(self.proxy_auth) if self.proxy_auth else None,
            "params": self.params,
            "trust_env": self.trust_env,
            "allow_redirects": self.allow_redirects,
            "max_redirects": self.max_redirects,
            "default_headers": self.default_headers,
            "default_encoding": self.default_encoding,
            "http_version": self.http_version,
            "accept_encoding": self.accept_encoding,
            "stream": self.stream,
            "connector_limit": self._connector_limit,
            "connector_limit_per_host": self._max_per_host,
            "rate_limit": limiter_rate,
            "rate_limit_per_host": self._per_host_rate,
            "rate_limit_burst": self._rate_limit_burst,
            "rate_limit_jitter": self._rate_limit_jitter,
            "realistic_headers": self.realistic_headers,
            "think_time": list(self.think_time) if self.think_time is not None else None,
            "user_agent_rotation": self._serialize_user_agent_rotation(),
            "retries": {
                "total": retry.total,
                "backoff_factor": retry.backoff_factor,
                "max_backoff": retry.max_backoff,
                "jitter": retry.jitter,
                "status_forcelist": sorted(retry.status_forcelist),
                "allowed_methods": sorted(retry.allowed_methods),
                "respect_retry_after_header": retry.respect_retry_after_header,
            },
        }
        # Owner-only (0600) so cookies and proxy credentials stay private.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(os.fspath(path), flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)

    @classmethod
    async def load(cls, path: Union[str, "os.PathLike[str]"]) -> "Session":
        """Restore a session previously written by :meth:`save`.

        Raises:
            ValueError: If the file is not valid JSON or uses an unknown
                state format version.
        """
        try:
            with open(path, encoding="utf-8") as fh:
                state = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"not a valid session file: {path!r}") from exc
        if not isinstance(state, dict) or state.get("version") != cls._STATE_VERSION:
            raise ValueError(f"unsupported session state format: {path!r}")

        retries_state = state.get("retries") or {}
        timeout_value = state.get("timeout")
        if isinstance(timeout_value, list):
            timeout_value = tuple(timeout_value)
        rate_limit = state.get("rate_limit")
        think_time = state.get("think_time")
        if isinstance(think_time, list):
            think_time = tuple(think_time)
        ua_rotation = state.get("user_agent_rotation")
        return cls(
            headers=state.get("headers"),
            timeout=timeout_value,
            cookies=state.get("cookies"),
            proxies=state.get("proxies"),
            proxy=state.get("proxy"),
            proxy_auth=tuple(state["proxy_auth"]) if state.get("proxy_auth") else None,
            base_url=state.get("base_url"),
            params=state.get("params"),
            trust_env=bool(state.get("trust_env", True)),
            allow_redirects=bool(state.get("allow_redirects", True)),
            max_redirects=int(state.get("max_redirects", 30)),
            impersonate=state.get("impersonate"),
            default_headers=bool(state.get("default_headers", True)),
            default_encoding=state.get("default_encoding", "utf-8"),
            http_version=state.get("http_version", "auto"),
            accept_encoding=state.get("accept_encoding"),
            stream=bool(state.get("stream", False)),
            connector_limit=int(state.get("connector_limit", 100)),
            connector_limit_per_host=int(state.get("connector_limit_per_host", 0)),
            rate_limit=float(rate_limit) if rate_limit is not None else None,
            rate_limit_per_host=state.get("rate_limit_per_host"),
            rate_limit_burst=int(state.get("rate_limit_burst", 1)),
            rate_limit_jitter=float(state.get("rate_limit_jitter", 0.0)),
            realistic_headers=bool(state.get("realistic_headers", False)),
            think_time=think_time,
            user_agent_rotation=ua_rotation,
            retries=RetryPolicy(
                total=retries_state.get("total", 0),
                backoff_factor=retries_state.get("backoff_factor", 0.25),
                max_backoff=retries_state.get("max_backoff", 30.0),
                jitter=retries_state.get("jitter", 0.1),
                status_forcelist=frozenset(retries_state.get("status_forcelist", ())),
                allowed_methods=frozenset(retries_state.get("allowed_methods", ())),
                respect_retry_after_header=bool(
                    retries_state.get("respect_retry_after_header", True)
                ),
            ),
        )

    _WS_KWARGS = frozenset(
        (
            "headers",
            "params",
            "cookies",
            "auth",
            "timeout",
            "allow_redirects",
            "max_redirects",
            "proxies",
            "proxy",
            "proxy_auth",
            "verify",
            "referer",
            "accept_encoding",
            "impersonate",
            "ja3",
            "akamai",
            "extra_fp",
        )
    )

    async def ws_connect(self, url: str, **kwargs: Any) -> "_AsyncSocketHandle":
        """Open an impersonated WebSocket connection.

        Accepts the same fingerprint/proxy/timeout options as :meth:`request`
        and inherits session defaults (headers, impersonate profile, proxy
        pool). Returns a handle delegating to the curl-impersonate socket
        (``send_str`` / ``recv_str`` / ``send_json`` / ``recv_json`` /
        ``ping``) that also works as an async context manager.

        Example:
            handle = await session.ws_connect("wss://echo.example")
            async with handle as ws:
                await ws.send_str("hello")
                print(await ws.recv_str())
        """
        if self._closed:
            raise RuntimeError("Session is closed")
        unknown = set(kwargs) - self._WS_KWARGS
        if unknown:
            raise TypeError(f"unexpected arguments for ws_connect: {sorted(unknown)}")

        target = urljoin(self.base_url.rstrip("/") + "/", url) if self.base_url else url
        if contains_control_characters(target):
            raise InvalidURL("WebSocket URL contains control characters")
        parts = urlsplit(target)
        if parts.scheme.lower() not in ("ws", "wss") or not parts.hostname:
            raise InvalidURL(f"invalid WebSocket URL: {strip_credentials(target)!r}")
        try:
            port = parts.port
        except ValueError as exc:
            raise InvalidURL(
                f"WebSocket URL has an invalid port: {strip_credentials(target)!r}"
            ) from exc
        if port is not None and not (1 <= port <= 65535):
            raise InvalidURL(f"WebSocket URL port out of range: {strip_credentials(target)!r}")

        options = {key: value for key, value in kwargs.items() if key in self._WS_KWARGS}
        merged_headers = self._headers.copy()
        user_headers = options.pop("headers", None)
        if user_headers is not None:
            merged_headers.update(user_headers)
        options["headers"] = merged_headers
        options.setdefault("timeout", self._timeout)
        options.setdefault("verify", self.verify)
        options.setdefault("impersonate", self.impersonate)
        if "ja3" not in options and self.ja3:
            options["ja3"] = self.ja3
        if "akamai" not in options and self.akamai:
            options["akamai"] = self.akamai
        if "extra_fp" not in options and self.extra_fp:
            options["extra_fp"] = self.extra_fp

        request_proxy = self.proxy if options.get("proxy") is None else options["proxy"]
        options.pop("proxy", None)
        request_proxies = self.proxies if options.get("proxies") is None else options["proxies"]
        options.pop("proxies", None)
        if isinstance(request_proxies, str):
            if request_proxy is not None:
                raise TypeError("cannot set both proxies as a string and proxy")
            request_proxy = request_proxies
            request_proxies = {}
        pool_proxy: str | None = None
        if self._proxy_pool is not None and request_proxy is None and not request_proxies:
            pool_proxy = self._proxy_pool.acquire()
            request_proxy = pool_proxy

        if request_proxies:
            options["proxies"] = request_proxies
        if request_proxy:
            options["proxy"] = request_proxy

        try:
            socket = await self._transport.ws_connect(target, **options)
        except Exception as exc:
            if pool_proxy is not None:
                self._proxy_pool.report_failure(pool_proxy)
            raise translate_exception(exc, target) from exc
        if pool_proxy is not None:
            self._proxy_pool.report_success(pool_proxy)
        return _AsyncSocketHandle(socket)

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
    "WebSocket",
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
