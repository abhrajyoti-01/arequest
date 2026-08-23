import asyncio
from collections import deque

import pytest
from curl_cffi.requests import Cookies, Headers

import arequest


class RawResponse:
    def __init__(
        self,
        status_code=200,
        content=b"ok",
        headers=None,
        chunks=None,
        url="https://example.test/resource",
    ):
        self.status_code = status_code
        self.content = content
        self.headers = Headers(headers)
        self.url = url
        self.reason = "OK" if status_code < 400 else "Error"
        self.elapsed = 0.01
        self.cookies = Cookies()
        self.history = []
        self.redirect_count = 0
        self.redirect_url = ""
        self.http_version = 2
        self.primary_ip = "127.0.0.1"
        self.primary_port = 443
        self.local_ip = "127.0.0.1"
        self.local_port = 12345
        self.infos = {}
        self.request = None
        self.queue = object() if chunks is not None else None
        self.quit_now = asyncio.Event() if chunks is not None else None
        self._chunks = list(chunks or [])
        self.closed = False

    @property
    def encoding(self):
        return "utf-8"

    async def aiter_content(self):
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk

    async def acontent(self):
        return b"".join([chunk async for chunk in self.aiter_content()])

    async def aclose(self):
        self.closed = True


class FakeTransport:
    name = "fake"

    def __init__(self, *results):
        self.results = deque(results)
        self.requests = []
        self.cookies = Cookies()
        self.closed = False

    async def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        result = self.results.popleft()
        if isinstance(result, BaseException):
            raise result
        return result

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_session_prepares_browser_request_and_auth():
    transport = FakeTransport(RawResponse(content=b'{"ok":true}'))
    async with arequest.Session(
        headers={"X-Session": "one"},
        timeout=arequest.Timeout(connect=1, read=2),
        auth=arequest.BasicAuth("user", "pass"),
        http_version="h2",
        transport=transport,
    ) as session:
        response = await session.get(
            "https://example.test/resource",
            headers={"X-Request": "two"},
            params={"page": 1},
        )

    method, url, kwargs = transport.requests[0]
    assert method == "GET"
    assert url == "https://example.test/resource"
    assert kwargs["headers"]["X-Session"] == "one"
    assert kwargs["headers"]["X-Request"] == "two"
    assert kwargs["headers"]["Authorization"].startswith("Basic ")
    assert kwargs["timeout"] == (1.0, 2.0)
    assert kwargs["impersonate"] == "chrome"
    assert kwargs["http_version"] == "v2"
    assert response.json() == {"ok": True}
    assert response.request_info.method == "GET"
    assert transport.closed


@pytest.mark.asyncio
async def test_status_and_transport_retries():
    transport = FakeTransport(
        RawResponse(status_code=503, headers={"Retry-After": "0"}),
        arequest.ConnectionError("temporary"),
        RawResponse(status_code=200),
    )
    async with arequest.Session(
        retries=2,
        backoff=0,
        transport=transport,
    ) as session:
        response = await session.get("https://example.test/resource")

    assert response.status_code == 200
    assert response.attempts == 3
    assert len(transport.requests) == 3


@pytest.mark.asyncio
async def test_post_is_not_retried_by_default():
    transport = FakeTransport(RawResponse(status_code=503), RawResponse(status_code=200))
    async with arequest.Session(retries=2, backoff=0, transport=transport) as session:
        response = await session.post("https://example.test/resource", json={"a": 1})

    assert response.status_code == 503
    assert response.attempts == 1
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_request_and_response_hooks_can_be_async():
    events = []

    async def request_hook(request):
        events.append("request")
        request.headers["X-Hook"] = "set"

    async def response_hook(response):
        events.append("response")
        response.from_hook = True

    transport = FakeTransport(RawResponse())
    async with arequest.Session(
        hooks={"request": request_hook, "response": response_hook},
        transport=transport,
    ) as session:
        response = await session.get("https://example.test/resource")

    assert events == ["request", "response"]
    assert transport.requests[0][2]["headers"]["X-Hook"] == "set"
    assert response.from_hook is True


@pytest.mark.asyncio
async def test_streaming_holds_concurrency_slot_until_consumed():
    first = RawResponse(chunks=[b"ab", b"cde", b"f\nsecond\n"])
    transport = FakeTransport(first, RawResponse(content=b"second response"))
    async with arequest.Session(connector_limit=1, transport=transport) as session:
        streamed = await session.get("https://example.test/stream", stream=True)
        pending = asyncio.create_task(session.get("https://example.test/next"))
        await asyncio.sleep(0)
        assert not pending.done()
        chunks = [chunk async for chunk in streamed.aiter_content(chunk_size=3)]
        second = await asyncio.wait_for(pending, timeout=1)

    assert chunks == [b"abc", b"def", b"\nse", b"con", b"d\n"]
    assert second.content == b"second response"
    assert first.closed


@pytest.mark.asyncio
async def test_streaming_lines_and_read():
    line_transport = FakeTransport(RawResponse(chunks=[b"first\r", b"\nsecond\nlast"]))
    async with arequest.Session(transport=line_transport) as session:
        response = await session.get("https://example.test/lines", stream=True)
        assert [line async for line in response.aiter_lines()] == [b"first", b"second", b"last"]

    read_transport = FakeTransport(RawResponse(chunks=[b"one", b"two"]))
    async with arequest.Session(transport=read_transport) as session:
        response = await session.get("https://example.test/read", stream=True)
        assert await response.read() == b"onetwo"
        assert response.content == b"onetwo"


@pytest.mark.asyncio
async def test_gather_accepts_all_request_spec_forms():
    transport = FakeTransport(RawResponse(), RawResponse(), RawResponse())
    async with arequest.Session(transport=transport) as session:
        responses = await session.gather(
            "https://example.test/one",
            ("POST", "https://example.test/two"),
            {"method": "PUT", "url": "https://example.test/three", "data": "x"},
        )

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [request[0] for request in transport.requests] == ["GET", "POST", "PUT"]


@pytest.mark.asyncio
async def test_invalid_url_and_closed_session_errors():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(transport=transport)
    with pytest.raises(arequest.InvalidURL):
        await session.get("not-an-http-url")
    await session.close()
    with pytest.raises(RuntimeError, match="closed"):
        await session.get("https://example.test")
