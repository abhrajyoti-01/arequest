import codecs
import inspect
import json as stdlib_json
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from .exceptions import ClientError, ServerError, StreamError, translate_exception

try:
    import orjson
except ImportError:
    orjson = None


@dataclass(frozen=True)
class Timeout:
    total: Optional[float] = 30.0
    connect: Optional[float] = None
    read: Optional[float] = None

    def __post_init__(self) -> None:
        for value in (self.total, self.connect, self.read):
            if value is not None and value < 0:
                raise ValueError("timeout values cannot be negative")

    def as_curl(self) -> Union[float, tuple[float, float], None]:
        if self.connect is None and self.read is None:
            return self.total
        connect = self.connect if self.connect is not None else self.total
        read = self.read if self.read is not None else self.total
        if connect is None or read is None:
            raise ValueError("connect and read timeouts must both be defined")
        return float(connect), float(read)


TimeoutValue = Union[float, int, tuple[float, float], Timeout, None]


def normalize_timeout(value: TimeoutValue) -> Union[float, tuple[float, float], None]:
    if isinstance(value, Timeout):
        return value.as_curl()
    if value is None:
        return None
    if isinstance(value, tuple):
        if len(value) != 2:
            raise ValueError("timeout tuple must contain (connect, read)")
        connect, read = value
        if connect < 0 or read < 0:
            raise ValueError("timeout values cannot be negative")
        return float(connect), float(read)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timeout must be a number, a (connect, read) tuple, Timeout, or None")
    if value < 0:
        raise ValueError("timeout cannot be negative")
    return float(value)


@dataclass
class PreparedRequest:
    method: str
    url: str
    headers: Any
    attempt: int = 1


class Response:
    def __init__(
        self,
        raw: Any,
        *,
        request: Optional[PreparedRequest] = None,
        release: Optional[Callable[[], Any]] = None,
        attempts: int = 1,
    ) -> None:
        self.raw = raw
        self.status_code = int(getattr(raw, "status_code", 0))
        self.headers = getattr(raw, "headers", {})
        self.url = str(getattr(raw, "url", ""))
        self.reason = str(getattr(raw, "reason", ""))
        elapsed = getattr(raw, "elapsed", 0.0)
        self.elapsed = elapsed.total_seconds() if hasattr(elapsed, "total_seconds") else float(elapsed)
        self.cookies = getattr(raw, "cookies", {})
        self.history = [Response(item) for item in getattr(raw, "history", ())]
        self.request_info = request or self._request_from_raw(raw)
        self.request = self.request_info
        self.attempts = attempts
        self.redirect_count = int(getattr(raw, "redirect_count", len(self.history)))
        self.redirect_url = str(getattr(raw, "redirect_url", ""))
        self.http_version = getattr(raw, "http_version", None)
        self.primary_ip = str(getattr(raw, "primary_ip", ""))
        self.primary_port = int(getattr(raw, "primary_port", 0))
        self.local_ip = str(getattr(raw, "local_ip", ""))
        self.local_port = int(getattr(raw, "local_port", 0))
        self.infos = getattr(raw, "infos", {})
        self._release = release
        self._released = False
        self._streaming = getattr(raw, "queue", None) is not None
        self._stream_started = False
        self._stream_consumed = False
        self._encoding: Optional[str] = None

    @staticmethod
    def _request_from_raw(raw: Any) -> Optional[PreparedRequest]:
        request = getattr(raw, "request", None)
        if request is None:
            return None
        return PreparedRequest(
            method=str(getattr(request, "method", "")),
            url=str(getattr(request, "url", "")),
            headers=getattr(request, "headers", {}),
        )

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    @property
    def content(self) -> bytes:
        return bytes(getattr(self.raw, "content", b""))

    @property
    def encoding(self) -> str:
        if self._encoding is not None:
            return self._encoding
        encoding = getattr(self.raw, "encoding", None)
        return str(encoding or self._detect_encoding())

    @encoding.setter
    def encoding(self, value: str) -> None:
        self._encoding = value
        try:
            self.raw.encoding = value
        except (AttributeError, ValueError):
            pass

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding, errors="replace")

    @property
    def apparent_encoding(self) -> str:
        return self._detect_encoding()

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308) and bool(
            self._header("Location")
        )

    @property
    def is_permanent_redirect(self) -> bool:
        return self.status_code in (301, 308) and bool(self._header("Location"))

    @property
    def links(self) -> Mapping[str, Any]:
        return {}

    def _header(self, name: str, default: Any = None) -> Any:
        if hasattr(self.headers, "get"):
            value = self.headers.get(name)
            if value is not None:
                return value
        target = name.lower()
        for key, value in getattr(self.headers, "items", lambda: ())():
            if str(key).lower() == target:
                return value
        return default

    def _detect_encoding(self) -> str:
        content_type = str(self._header("Content-Type", ""))
        marker = "charset="
        if marker in content_type.lower():
            start = content_type.lower().find(marker) + len(marker)
            return content_type[start:].split(";", 1)[0].strip(" \t\"'") or "utf-8"
        return "utf-8"

    def decode(self, encoding: Optional[str] = None) -> str:
        return self.content.decode(encoding or self.encoding, errors="replace")

    def json(self, **kwargs: Any) -> Any:
        if orjson is not None and not kwargs:
            return orjson.loads(self.content)
        return stdlib_json.loads(self.text, **kwargs)

    def raise_for_status(self) -> None:
        if 400 <= self.status_code < 500:
            raise ClientError(
                f"{self.status_code} Client Error: {self.reason} for {self.url}",
                self.status_code,
                self,
            )
        if self.status_code >= 500:
            raise ServerError(
                f"{self.status_code} Server Error: {self.reason} for {self.url}",
                self.status_code,
                self,
            )

    def iter_content(self, chunk_size: int = 65536) -> Iterator[bytes]:
        if self._streaming and not self._stream_consumed:
            raise StreamError("use 'async for' with aiter_content() for a streaming response")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        body = self.content
        for offset in range(0, len(body), chunk_size):
            yield body[offset : offset + chunk_size]

    def iter_lines(self, delimiter: bytes = b"\n") -> Iterator[bytes]:
        if not delimiter:
            raise ValueError("delimiter cannot be empty")
        for line in self.content.split(delimiter):
            yield line.rstrip(b"\r")

    async def read(self) -> bytes:
        if not self._streaming:
            return self.content
        if self._stream_started:
            raise StreamError("stream has already been consumed")
        self._stream_started = True
        try:
            content = await self.raw.acontent()
            self.raw.content = content
            self._stream_consumed = True
            self._streaming = False
            return content
        except Exception as exc:
            raise translate_exception(exc, self.url) from exc
        finally:
            await self._release_once()

    async def aiter_content(
        self,
        chunk_size: Optional[int] = 65536,
        decode_unicode: bool = False,
    ) -> AsyncIterator[Any]:
        if chunk_size is not None and chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if not self._streaming:
            decoder = codecs.getincrementaldecoder(self.encoding)(errors="replace") if decode_unicode else None
            for chunk in self.iter_content(chunk_size or max(1, len(self.content))):
                yield decoder.decode(chunk) if decoder else chunk
            if decoder:
                tail = decoder.decode(b"", final=True)
                if tail:
                    yield tail
            return
        if self._stream_started:
            raise StreamError("stream has already been consumed")

        self._stream_started = True
        pending = bytearray()
        decoder = codecs.getincrementaldecoder(self.encoding)(errors="replace") if decode_unicode else None
        try:
            async for incoming in self.raw.aiter_content():
                if chunk_size is None:
                    yield decoder.decode(incoming) if decoder else incoming
                    continue
                pending.extend(incoming)
                while len(pending) >= chunk_size:
                    chunk = bytes(pending[:chunk_size])
                    del pending[:chunk_size]
                    yield decoder.decode(chunk) if decoder else chunk
            if pending:
                chunk = bytes(pending)
                yield decoder.decode(chunk) if decoder else chunk
            if decoder:
                tail = decoder.decode(b"", final=True)
                if tail:
                    yield tail
            self._stream_consumed = True
        except Exception as exc:
            raise translate_exception(exc, self.url) from exc
        finally:
            await self._close_raw_stream()
            await self._release_once()

    async def aiter_lines(
        self,
        delimiter: bytes = b"\n",
        decode_unicode: bool = False,
    ) -> AsyncIterator[Any]:
        if not delimiter:
            raise ValueError("delimiter cannot be empty")
        pending = bytearray()
        async for chunk in self.aiter_content(chunk_size=None):
            pending.extend(chunk)
            while True:
                index = pending.find(delimiter)
                if index < 0:
                    break
                line = bytes(pending[:index]).rstrip(b"\r")
                del pending[: index + len(delimiter)]
                yield line.decode(self.encoding, errors="replace") if decode_unicode else line
        if pending:
            line = bytes(pending).rstrip(b"\r")
            yield line.decode(self.encoding, errors="replace") if decode_unicode else line

    async def _close_raw_stream(self) -> None:
        if not self._streaming:
            return
        quit_now = getattr(self.raw, "quit_now", None)
        if quit_now is not None and not self._stream_consumed:
            quit_now.set()
        close = getattr(self.raw, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception as exc:
                if not self._stream_consumed:
                    raise translate_exception(exc, self.url) from exc

    async def _release_once(self) -> None:
        if self._released or self._release is None:
            return
        self._released = True
        result = self._release()
        if inspect.isawaitable(result):
            await result

    async def aclose(self) -> None:
        try:
            await self._close_raw_stream()
        finally:
            await self._release_once()

    def close(self) -> None:
        quit_now = getattr(self.raw, "quit_now", None)
        if quit_now is not None:
            quit_now.set()
        if not self._released and self._release is not None:
            result = self._release()
            if inspect.isawaitable(result):
                raise RuntimeError("use await response.aclose() to close this response")
            self._released = True

    async def __aenter__(self) -> "Response":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"<Response [{self.status_code}]>"
