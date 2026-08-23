from typing import Any


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

    try:
        from curl_cffi.requests import exceptions as curl_errors
    except ImportError:
        return TransportError(str(exc) or exc.__class__.__name__)

    response = getattr(exc, "response", None)
    request = getattr(response, "request", None)
    target = f" for {url}" if url else ""
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
