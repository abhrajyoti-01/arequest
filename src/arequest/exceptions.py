from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    from curl_cffi.requests import exceptions as _curl_errors
except ImportError:  # pragma: no cover - curl_cffi is a hard dependency
    _curl_errors = None


def strip_credentials(url: str | None) -> str | None:
    """Mask ``user:password`` userinfo in a URL so it is safe to log.

    Best-effort: if the URL cannot be parsed, it is returned unchanged.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if parts.username is None and parts.password is None:
            return url
        netloc = parts.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return url


def contains_control_characters(url: str) -> bool:
    """Return True if the URL contains characters that must not appear in one."""
    return any(ord(char) < 0x20 or ord(char) == 0x7F for char in url)


class RequestError(Exception):
    def __init__(
        self,
        message: str,
        *,
        request: Any = None,
        response: Any = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.request = request
        self.response = response
        self.retryable = retryable


class TransportError(RequestError):
    pass


class ConnectionError(TransportError):
    def __init__(self, message: str, *, request: Any = None, response: Any = None) -> None:
        super().__init__(message, request=request, response=response, retryable=True)


class TimeoutError(TransportError):
    def __init__(self, message: str, *, request: Any = None, response: Any = None) -> None:
        super().__init__(message, request=request, response=response, retryable=True)


class ProxyError(ConnectionError):
    pass


class SSLError(TransportError):
    pass


class InvalidURL(RequestError, ValueError):
    pass


class TooManyRedirects(RequestError):
    pass


class ImpersonationError(RequestError, ValueError):
    pass


class StreamError(RequestError):
    pass


class HTTPError(RequestError):
    def __init__(
        self,
        message: str,
        status_code: int,
        response: Any = None,
    ) -> None:
        super().__init__(
            message,
            request=getattr(response, "request_info", None),
            response=response,
            retryable=False,
        )
        self.status_code = status_code


class ClientError(HTTPError):
    pass


class ServerError(HTTPError):
    pass


def translate_exception(exc: BaseException, url: str | None = None) -> RequestError:
    if isinstance(exc, RequestError):
        return exc

    curl_errors = _curl_errors
    if curl_errors is None:
        return TransportError(str(exc) or exc.__class__.__name__)

    response = getattr(exc, "response", None)
    request = getattr(response, "request", None)
    target = f" for {strip_credentials(url)}" if url else ""
    message = f"{exc}{target}"

    if isinstance(exc, curl_errors.ImpersonateError):
        return ImpersonationError(message, request=request, response=response)
    if isinstance(exc, curl_errors.TooManyRedirects):
        return TooManyRedirects(message, request=request, response=response)
    if isinstance(
        exc,
        (
            curl_errors.InvalidURL,
            curl_errors.InvalidSchema,
            curl_errors.MissingSchema,
            curl_errors.URLRequired,
        ),
    ):
        return InvalidURL(message, request=request, response=response)
    if isinstance(exc, curl_errors.Timeout):
        return TimeoutError(message, request=request, response=response)
    if isinstance(exc, curl_errors.ProxyError):
        return ProxyError(message, request=request, response=response)
    if isinstance(exc, curl_errors.SSLError):
        return SSLError(message, request=request, response=response)
    if isinstance(exc, (curl_errors.DNSError, curl_errors.ConnectionError)):
        return ConnectionError(message, request=request, response=response)
    if isinstance(exc, curl_errors.RequestException):
        return TransportError(message, request=request, response=response)
    return TransportError(message)
