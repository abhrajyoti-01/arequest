from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin, urlsplit

from curl_cffi.requests import AsyncSession, Cookies, Headers

from .exceptions import (
    InvalidURL,
    TooManyRedirects,
    contains_control_characters,
    strip_credentials,
    translate_exception,
)

_HTTP_VERSIONS = {
    "auto": None,
    "1": "v1",
    "1.1": "v1",
    "h1": "v1",
    "http1": "v1",
    "http/1.1": "v1",
    "v1": "v1",
    "2": "v2",
    "h2": "v2",
    "http2": "v2",
    "http/2": "v2",
    "v2": "v2",
    "v2tls": "v2tls",
    "v2_prior_knowledge": "v2_prior_knowledge",
    "3": "v3",
    "h3": "v3",
    "http3": "v3",
    "http/3": "v3",
    "v3": "v3",
    "v3only": "v3only",
}


def normalize_http_version(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in _HTTP_VERSIONS:
        supported = ", ".join(sorted(_HTTP_VERSIONS))
        raise ValueError(f"unsupported HTTP version {value!r}; expected one of: {supported}")
    return _HTTP_VERSIONS[normalized]


def _origin(url: str) -> tuple:
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = None
    port = port or (443 if parts.scheme.lower() == "https" else 80)
    return parts.scheme.lower(), (parts.hostname or "").lower(), port


class CurlTransport:
    name = "curl_cffi"

    def __init__(
        self,
        *,
        max_clients: int = 100,
        cookies: Any = None,
        trust_env: bool = True,
        debug: bool = False,
        curl_options: Mapping[Any, Any] | None = None,
        curl_infos: Any = None,
    ) -> None:
        if max_clients < 1:
            raise ValueError("max_clients must be at least one")
        self._session = AsyncSession(
            max_clients=max_clients,
            cookies=cookies,
            trust_env=trust_env,
            debug=debug,
            curl_options=dict(curl_options or {}),
            curl_infos=curl_infos,
        )
        self._closed = False

    @property
    def cookies(self) -> Cookies:
        return self._session.cookies

    @property
    def raw_session(self) -> AsyncSession:
        return self._session

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self._closed:
            raise RuntimeError("transport is closed")
        try:
            return await self._request_with_redirects(method, url, kwargs)
        except Exception as exc:
            if isinstance(exc, (InvalidURL, TooManyRedirects)):
                raise
            raise translate_exception(exc, url) from exc

    async def ws_connect(self, url: str, **kwargs: Any) -> Any:
        if self._closed:
            raise RuntimeError("transport is closed")
        try:
            return await self._session.ws_connect(url, **kwargs)
        except Exception as exc:
            raise translate_exception(exc, url) from exc

    async def _request_with_redirects(
        self,
        method: str,
        url: str,
        kwargs: Mapping[str, Any],
    ) -> Any:
        options = dict(kwargs)
        allow_redirects = bool(options.pop("allow_redirects", True))
        max_redirects = int(options.pop("max_redirects", 30))
        if not allow_redirects:
            return await self._session.request(
                method,
                url,
                allow_redirects=False,
                max_redirects=max_redirects,
                **options,
            )

        current_method = method.upper()
        current_url = url
        history = []
        while True:
            response = await self._session.request(
                current_method,
                current_url,
                allow_redirects=False,
                max_redirects=max_redirects,
                **options,
            )
            location = response.headers.get("Location")
            if response.status_code not in (301, 302, 303, 307, 308) or not location:
                response.history = history
                response.redirect_count = len(history)
                return response
            if len(history) >= max_redirects:
                await self._discard_stream(response)
                raise TooManyRedirects(
                    f"Exceeded {max_redirects} redirects for {strip_credentials(url)}",
                    request=getattr(response, "request", None),
                    response=response,
                )

            next_url = urljoin(current_url, location)
            if contains_control_characters(next_url):
                await self._discard_stream(response)
                raise InvalidURL("redirect URL contains control characters")
            parts = urlsplit(next_url)
            if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
                await self._discard_stream(response)
                raise InvalidURL(f"invalid redirect URL: {strip_credentials(next_url)!r}")
            try:
                port = parts.port
            except ValueError:
                port = -1
            if port is not None and not (1 <= port <= 65535):
                await self._discard_stream(response)
                raise InvalidURL(
                    f"redirect URL has an out-of-range port: {strip_credentials(next_url)!r}"
                )

            history.append(response)
            await self._discard_stream(response)
            next_method = current_method
            if response.status_code == 303 and current_method != "HEAD":
                next_method = "GET"
            elif response.status_code in (301, 302) and current_method == "POST":
                next_method = "GET"

            cross_origin = _origin(current_url) != _origin(next_url)
            method_changed = next_method != current_method
            if cross_origin or method_changed:
                request_headers = Headers(options.get("headers"))
                if cross_origin:
                    for name in ("Authorization", "Cookie", "Host", "Proxy-Authorization"):
                        request_headers.pop(name, None)
                    options["auth"] = None
                    options["cookies"] = None
                if method_changed:
                    for name in ("Content-Length", "Content-Type", "Transfer-Encoding", "Origin"):
                        request_headers.pop(name, None)
                    options["data"] = None
                    options["json"] = None
                    options["files"] = None
                    options["multipart"] = None
                options["headers"] = request_headers
            current_method = next_method
            current_url = next_url

    @staticmethod
    async def _discard_stream(response: Any) -> None:
        quit_now = getattr(response, "quit_now", None)
        if quit_now is not None:
            quit_now.set()
        close = getattr(response, "aclose", None)
        if close is not None:
            await close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._session.close()


def create_cookie_jar(cookies: Any = None) -> Cookies:
    if isinstance(cookies, Cookies):
        return cookies
    return Cookies(cookies)
