import asyncio
import json
from collections import deque

import pytest
from aiohttp import WSMsgType, web
from curl_cffi.requests import Cookies, Headers

import arequest
from arequest.exceptions import ConnectionError, InvalidURL, ProxyError


class RawResponse:
    def __init__(self, content=b"ok", url="https://example.test/resource"):
        self.status_code = 200
        self.content = content
        self.headers = Headers()
        self.url = url
        self.reason = "OK"
        self.elapsed = 0.01
        self.cookies = Cookies()
        self.history = []
        self.redirect_count = 0
        self.redirect_url = ""
        self.http_version = 2
        self.primary_ip = "127.0.0.1"
        self.primary_port = 443
        self.local_ip = "127.0.0.1"
        self.local_port = 1
        self.infos = {}
        self.request = None
        self.queue = None
        self.quit_now = None


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


async def _start_app(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port


async def test_iter_fetch_respects_max_concurrency():
    state = {"current": 0, "peak": 0}

    async def handler(request):
        state["current"] += 1
        state["peak"] = max(state["peak"], state["current"])
        await asyncio.sleep(0.05)
        state["current"] -= 1
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    runner, port = await _start_app(app)
    try:
        urls = [f"http://127.0.0.1:{port}/{i}" for i in range(8)]
        results = []
        async with arequest.Session() as session:
            async for response in session.iter_fetch(urls, max_concurrency=2):
                results.append(response.status_code)
        assert len(results) == 8
        assert all(code == 200 for code in results)
        assert state["peak"] <= 2
    finally:
        await runner.cleanup()


async def test_iter_fetch_return_exceptions():
    async def handler(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    runner, port = await _start_app(app)
    try:
        urls = [f"http://127.0.0.1:{port}/good", "ftp://bad.example/file"]
        async with arequest.Session() as session:
            collected = [
                item
                async for item in session.iter_fetch(
                    urls, max_concurrency=2, return_exceptions=True
                )
            ]
        kinds = sorted(type(item).__name__ for item in collected)
        assert kinds == ["InvalidURL", "Response"]
    finally:
        await runner.cleanup()


async def test_save_load_roundtrip(tmp_path):
    async def set_cookie(request):
        response = web.Response(text="set")
        response.set_cookie("token", "abc123", path="/")
        return response

    app = web.Application()
    app.router.add_get("/set", set_cookie)
    runner, port = await _start_app(app)
    try:
        source = arequest.Session(
            headers={"X-Custom": "yes"},
            timeout=(1.5, 5.5),
            impersonate="chrome131",
            base_url=f"http://127.0.0.1:{port}",
            retries=arequest.RetryPolicy(total=2, backoff_factor=0.5),
            rate_limit=25.0,
            connector_limit=7,
            allow_redirects=False,
        )
        async with source:
            await source.get("/set")
        assert dict(source.cookies)

        path = tmp_path / "state.json"
        await source.save(path)
        restored = await arequest.Session.load(path)

        assert dict(restored.cookies) == dict(source.cookies)
        assert dict(restored.headers) == dict(source.headers)
        assert restored.timeout == (1.5, 5.5)
        assert restored.impersonate == "chrome131"
        assert restored.base_url == f"http://127.0.0.1:{port}"
        assert restored.retry_policy.total == 2
        assert restored.retry_policy.backoff_factor == 0.5
        assert restored.retry_policy.status_forcelist == frozenset((429, 500, 502, 503, 504))
        assert restored._rate_limiter.rate == 25.0
        assert restored._connector_limit == 7
        assert restored.allow_redirects is False
    finally:
        await runner.cleanup()


async def test_load_rejects_corrupt_file(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        await arequest.Session.load(path)


def test_proxy_pool_round_robin_rotation():
    pool = arequest.ProxyPool(["http://a:1", "http://b:2", "http://c:3"])
    picked = [pool.acquire(), pool.acquire(), pool.acquire()]
    assert picked == ["http://a:1", "http://b:2", "http://c:3"]
    assert all(pool.status().values())


def test_proxy_pool_failure_cooldown_and_exhaustion():
    pool = arequest.ProxyPool(["http://a:1", "http://b:2"], cooldown=60.0)
    first = pool.acquire()
    pool.report_failure(first)
    status = pool.status()
    assert status[first] is False
    assert status["http://b:2"] is True
    remaining = pool.acquire()
    assert remaining != first
    pool.report_failure(remaining)
    with pytest.raises(ProxyError):
        pool.acquire()

    pool.report_success(first)
    assert pool.status()[first] is True


def test_proxy_pool_strategies():
    failover = arequest.ProxyPool(["http://a:1", "http://b:2"], strategy="failover")
    assert failover.acquire() == "http://a:1"
    failover.report_failure("http://a:1")
    assert failover.acquire() == "http://b:2"

    random_pool = arequest.ProxyPool(["http://a:1", "http://b:2"], strategy="random")
    assert random_pool.acquire() in ("http://a:1", "http://b:2")

    with pytest.raises(ValueError):
        arequest.ProxyPool(["http://a:1"], strategy="chaos")
    with pytest.raises(ValueError):
        arequest.ProxyPool([])
    with pytest.raises(ValueError):
        arequest.ProxyPool(["not-a-proxy"])


def test_session_rotates_pool_proxies():
    transport = FakeTransport(RawResponse(), RawResponse())
    session = arequest.Session(
        proxy_pool=["http://p1:8080", "http://p2:8080"],
        impersonate=None,
        transport=transport,
    )
    asyncio.run(session.get("https://example.test/one"))
    asyncio.run(session.get("https://example.test/two"))
    proxies_used = [call[2].get("proxy") for call in transport.requests]
    assert proxies_used == ["http://p1:8080", "http://p2:8080"]
    assert all(session.proxy_pool.status().values())
    asyncio.run(session.close())


def test_session_marks_failed_proxy_unhealthy():
    transport = FakeTransport(ConnectionError("boom"), RawResponse(), RawResponse())
    session = arequest.Session(
        proxy_pool=["http://dead:1", "http://alive:2"],
        impersonate=None,
        transport=transport,
    )
    with pytest.raises(ConnectionError):
        asyncio.run(session.get("https://example.test/x"))
    assert session.proxy_pool.status()["http://dead:1"] is False
    asyncio.run(session.close())


async def test_websocket_echo():
    async def echo(request):
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        seen_header = request.headers.get("X-Session")
        async for msg in socket:
            if msg.type != WSMsgType.TEXT:
                break
            try:
                payload = json.loads(msg.data)
                await socket.send_str(
                    json.dumps({"echo": payload, "header": seen_header})
                )
            except json.JSONDecodeError:
                await socket.send_str("echo:" + msg.data)

    app = web.Application()
    app.router.add_get("/ws", echo)
    runner, port = await _start_app(app)
    try:
        async with arequest.Session(headers={"X-Session": "s1"}) as session:
            async with await session.ws_connect(f"ws://127.0.0.1:{port}/ws") as ws:
                await ws.send_json({"hello": "world"})
                payload = await ws.recv_json()
                assert payload["echo"] == {"hello": "world"}
                assert payload["header"] == "s1"

                await ws.send_str("plain")
                assert await ws.recv_str() == "echo:plain"
    finally:
        await runner.cleanup()


async def test_ws_connect_rejects_bad_url_and_kwargs():
    async with arequest.Session() as session:
        with pytest.raises(InvalidURL):
            await session.ws_connect("gopher://nope")
        with pytest.raises(TypeError):
            await session.ws_connect("wss://example.test", bogus_option=1)


def test_state_file_is_versioned(tmp_path):
    path = tmp_path / "state.json"
    session = arequest.Session(impersonate=None)
    asyncio.run(session.save(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == arequest.Session._STATE_VERSION
