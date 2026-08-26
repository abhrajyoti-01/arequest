import asyncio
import time
from collections import deque

import pytest
from aiohttp import web
from curl_cffi.requests import Cookies, Headers

import arequest
from arequest.limits import AsyncRateLimiter
from arequest.models import Response


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
        if self.results:
            result = self.results.popleft()
            if isinstance(result, BaseException):
                raise result
            return result
        return RawResponse(url=url)

    async def close(self):
        self.closed = True


async def _start_app(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port


# --- AsyncRateLimiter (token bucket + jitter) ---------------------------------


def test_rate_limiter_repr_and_validation():
    limiter = AsyncRateLimiter(10, burst=2, jitter=0.05)
    assert "rate=10.0" in repr(limiter)
    assert "jitter=0.05" in repr(limiter)
    with pytest.raises(ValueError):
        AsyncRateLimiter(0)
    with pytest.raises(ValueError):
        AsyncRateLimiter(1, burst=0)
    with pytest.raises(ValueError):
        AsyncRateLimiter(1, jitter=-1)


async def test_rate_limiter_burst_then_paces():
    limiter = AsyncRateLimiter(rate=50, burst=2)
    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    assert (time.monotonic() - start) < 0.1

    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    # Two more tokens at 50 rps -> ~0.04s; assert comfortably above the Windows
    # timer-resolution floor.
    assert (time.monotonic() - start) >= 0.03


async def test_rate_limiter_fifo_no_thundering_herd():
    limiter = AsyncRateLimiter(rate=100, burst=1)
    await limiter.acquire()  # drain the burst token
    order = []

    async def worker(i):
        await limiter.acquire()
        order.append(i)

    tasks = [asyncio.ensure_future(worker(i)) for i in range(4)]
    await asyncio.sleep(0)
    await asyncio.gather(*tasks)
    assert order == [0, 1, 2, 3]


# --- Response lazy history ----------------------------------------------------


def test_response_history_lazy_no_redirect():
    raw = RawResponse()
    resp = Response(raw)
    assert resp.redirect_count == 0
    assert resp._history is None  # not built until accessed
    assert resp.history == []  # built on demand


def test_response_history_lazy_builds_children():
    parent_raw = RawResponse(url="https://example.test/final")
    parent_raw.redirect_count = 1
    hop = RawResponse(url="https://example.test/start")
    hop.status_code = 301
    parent_raw.history = [hop]
    resp = Response(parent_raw)
    assert resp._history is None
    history = resp.history
    assert len(history) == 1
    assert history[0].status_code == 301
    assert resp.redirect_count == 1


def test_response_history_setter():
    resp = Response(RawResponse())
    resp.history = [Response(RawResponse())]
    assert len(resp.history) == 1


# --- Fast-path limiting flag --------------------------------------------------


def test_needs_limiting_flag_defaults():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(transport=transport)
    # Default connector_limit=100 -> semaphore present -> limiting required.
    assert session._needs_limiting is True


def test_needs_limiting_flag_fast_path():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(
        transport=transport, connector_limit=0, connector_limit_per_host=0
    )
    assert session._needs_limiting is False


def test_needs_limiting_flag_with_rate_limit():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(
        transport=transport, connector_limit=0, connector_limit_per_host=0, rate_limit=5
    )
    assert session._needs_limiting is True


# --- Realistic headers ---------------------------------------------------------


async def test_realistic_headers_added_without_clobbering():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(
        transport=transport,
        impersonate="chrome",
        realistic_headers=True,
        headers={"Accept-Language": "fr-FR"},
    )
    resp = await session.get("https://example.test/")
    assert resp.status_code == 200
    sent = transport.requests[-1][2]["headers"]
    assert sent.get("Accept-Language") == "fr-FR"  # caller-set preserved
    assert sent.get("Upgrade-Insecure-Requests") == "1"
    assert "Sec-Fetch-Dest" in sent
    assert "Sec-CH-UA" in sent


async def test_realistic_headers_off_by_default():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(transport=transport)
    await session.get("https://example.test/")
    sent = transport.requests[-1][2]["headers"]
    assert "Sec-Fetch-Dest" not in sent
    assert "Upgrade-Insecure-Requests" not in sent


# --- User-Agent rotation -------------------------------------------------------


async def test_user_agent_rotation_explicit_pool():
    pool = ["Agent-A", "Agent-B"]
    transport = FakeTransport(RawResponse())
    session = arequest.Session(transport=transport, user_agent_rotation=pool)
    async with session:
        await session.get("https://example.test/1")
        await session.get("https://example.test/2")
        await session.get("https://example.test/3")
    uas = [req[2]["headers"].get("User-Agent") for req in transport.requests]
    assert uas[0] == "Agent-A"
    assert uas[1] == "Agent-B"
    assert uas[2] == "Agent-A"  # wraps around


async def test_user_agent_rotation_auto_chrome():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(
        transport=transport, impersonate="chrome", user_agent_rotation="auto"
    )
    await session.get("https://example.test/")
    ua = transport.requests[-1][2]["headers"].get("User-Agent")
    assert "Chrome/" in ua


async def test_user_agent_rotation_none_default():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(transport=transport)
    await session.get("https://example.test/")
    sent = transport.requests[-1][2]["headers"]
    assert sent.get("User-Agent") is None


# --- think_time ----------------------------------------------------------------


async def test_think_time_validation():
    transport = FakeTransport(RawResponse())
    with pytest.raises(ValueError):
        arequest.Session(transport=transport, think_time=-1)
    with pytest.raises(TypeError):
        arequest.Session(transport=transport, think_time="soon")


async def test_think_time_paces_requests():
    transport = FakeTransport(RawResponse())
    session = arequest.Session(transport=transport, think_time=0.1)
    async with session:
        # Prime the clock as if a request just started, then verify the next
        # request is delayed by the full think_time interval.
        session._last_request_at = time.monotonic()
        start = time.monotonic()
        await session.get("https://example.test/2")
        elapsed = time.monotonic() - start
    assert elapsed >= 0.09


# --- save/load roundtrip of new options ----------------------------------------


async def test_save_load_roundtrip_new_options(tmp_path):
    transport = FakeTransport(RawResponse())
    session = arequest.Session(
        transport=transport,
        realistic_headers=True,
        think_time=(0.1, 0.5),
        user_agent_rotation=["X", "Y"],
        rate_limit_jitter=0.02,
    )
    path = tmp_path / "state.json"
    await session.save(path)
    loaded = await arequest.Session.load(path)
    assert loaded.realistic_headers is True
    assert loaded.think_time == (0.1, 0.5)
    assert loaded._rate_limit_jitter == pytest.approx(0.02)
    assert loaded.user_agent_rotation is not None


# --- iter_fetch: errors + graceful shutdown ------------------------------------


async def test_iter_fetch_raises_and_shuts_down_cleanly():
    async def slow_handler(request):
        await asyncio.sleep(0.05)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/{tail:.*}", slow_handler)
    runner, port = await _start_app(app)
    try:
        good = f"http://127.0.0.1:{port}/good"
        urls = [good, "ftp://bad.example/file", good, good]
        async with arequest.Session() as session:
            with pytest.raises(arequest.InvalidURL):
                async for _ in session.iter_fetch(urls, max_concurrency=2):
                    pass  # first error should abort iteration
    finally:
        await runner.cleanup()

