import pytest
from aiohttp import web

import arequest


@pytest.fixture
async def local_server():
    state = {"retries": 0}

    async def echo(request):
        payload = await request.read()
        return web.json_response(
            {
                "method": request.method,
                "query": dict(request.query),
                "body": payload.decode(),
                "user_agent": request.headers.get("User-Agent"),
                "cookie": request.cookies.get("session"),
            }
        )

    async def set_cookie(request):
        response = web.Response(text="set")
        response.set_cookie("session", "persisted", path="/")
        return response

    async def redirect(request):
        raise web.HTTPFound("/final")

    async def final(request):
        return web.Response(text="final")

    async def retry(request):
        state["retries"] += 1
        if state["retries"] < 3:
            return web.Response(status=503, headers={"Retry-After": "0"})
        return web.Response(text="recovered")

    async def stream(request):
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(b"alpha\n")
        await response.write(b"beta\n")
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_route("*", "/echo", echo)
    app.router.add_get("/set-cookie", set_cookie)
    app.router.add_get("/redirect", redirect)
    app.router.add_get("/final", final)
    app.router.add_get("/retry", retry)
    app.router.add_get("/stream", stream)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", state
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_real_transport_request_cookie_redirect_retry_and_stream(local_server):
    base_url, state = local_server
    async with arequest.Session(
        base_url=base_url,
        retries=2,
        backoff=0,
        trust_env=False,
    ) as session:
        posted = await session.post("/echo?source=test", data="payload")
        assert posted.json()["method"] == "POST"
        assert posted.json()["query"] == {"source": "test"}
        assert posted.json()["body"] == "payload"
        assert posted.json()["user_agent"].startswith("Mozilla/5.0")

        await session.get("/set-cookie")
        cookie_echo = await session.get("/echo")
        assert cookie_echo.json()["cookie"] == "persisted"

        redirected = await session.get("/redirect")
        assert redirected.status_code == 200
        assert redirected.text == "final"
        assert redirected.history

        retried = await session.get("/retry")
        assert retried.status_code == 200
        assert retried.attempts == 3
        assert state["retries"] == 3

        streamed = await session.get("/stream", stream=True)
        assert [line async for line in streamed.aiter_lines()] == [b"alpha", b"beta"]


@pytest.mark.asyncio
async def test_real_transport_can_disable_impersonation(local_server):
    base_url, _ = local_server
    async with arequest.Session(
        base_url=base_url,
        impersonate=None,
        default_headers=False,
        trust_env=False,
    ) as session:
        response = await session.get("/echo", headers={"User-Agent": "custom-agent"})
    assert response.json()["user_agent"] == "custom-agent"
