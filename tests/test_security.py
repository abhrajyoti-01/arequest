"""Security regression tests: credential masking, URL validation, file perms."""

import os
import sys

import pytest
from aiohttp import web

import arequest
from arequest.exceptions import (
    InvalidURL,
    TransportError,
    contains_control_characters,
    strip_credentials,
    translate_exception,
)
from arequest.proxypool import ProxyPool

SECRET = "s3cret-pw"
CRED_URL = f"https://alice:{SECRET}@example.test/path"


async def _start_app(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port


# --- strip_credentials / contains_control_characters --------------------------


def test_strip_credentials_masks_userinfo():
    assert strip_credentials(CRED_URL) == "https://example.test/path"
    # Only username present.
    assert strip_credentials("https://bob@example.test/x") == "https://example.test/x"
    # Plain URLs untouched.
    assert strip_credentials("https://example.test/x?user=carol") == (
        "https://example.test/x?user=carol"
    )
    assert strip_credentials(None) is None


def test_contains_control_characters():
    assert contains_control_characters("https://h/\x0b")
    assert contains_control_characters("https://h/\x00")
    assert contains_control_characters("https://h\x7f/")
    assert not contains_control_characters("https://h/~p%20q")


# --- V1: exception messages never leak credentials ----------------------------


def test_translate_exception_masks_url():
    err = translate_exception(RuntimeError("boom"), CRED_URL)
    assert SECRET not in str(err)
    assert "example.test/path" in str(err)


async def test_connection_error_message_masks_credentials():
    async with arequest.Session() as session:
        with pytest.raises(Exception) as exc_info:  # noqa: PT011 - broad on purpose
            await session.get(f"https://alice:{SECRET}@127.0.0.1:1/x")
    assert SECRET not in str(exc_info.value)


async def test_invalidurl_message_masks_credentials():
    async with arequest.Session() as session:
        with pytest.raises(InvalidURL) as exc_info:
            await session.get(f"ftp://alice:{SECRET}@example.test/x")
    assert SECRET not in str(exc_info.value)


# --- V2: session files are owner-only -----------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits not enforced on Windows"
)
async def test_save_file_owner_only_permissions(tmp_path):
    async with arequest.Session() as session:
        path = tmp_path / "state.json"
        await session.save(path)
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"


async def test_save_roundtrip_still_works(tmp_path):
    async with arequest.Session() as session:
        path = tmp_path / "state.json"
        await session.save(path)
        loaded = await arequest.Session.load(path)
        assert loaded.base_url == session.base_url


# --- V3/V4: redirect + URL validation ----------------------------------------


async def test_redirect_to_out_of_range_port_raises_invalidurl():
    async def handler(request):
        return web.Response(
            status=302, headers={"Location": "https://example.invalid:99999/next"}
        )

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    runner, port = await _start_app(app)
    try:
        async with arequest.Session(max_redirects=5) as session:
            with pytest.raises(arequest.InvalidURL):
                await session.get(f"http://127.0.0.1:{port}/start")
    finally:
        await runner.cleanup()


async def test_redirect_with_control_character_raises_invalidurl():
    async def handler(request):
        return web.Response(
            status=302, headers={"Location": "https://example.invalid/\x0bnext"}
        )

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    runner, port = await _start_app(app)
    try:
        async with arequest.Session(max_redirects=5) as session:
            with pytest.raises(arequest.InvalidURL):
                await session.get(f"http://127.0.0.1:{port}/start")
    finally:
        await runner.cleanup()


async def test_request_url_control_characters_rejected():
    async with arequest.Session() as session:
        with pytest.raises(InvalidURL):
            await session.get("https://example.test/\x0bpath")
        with pytest.raises(InvalidURL):
            await session.get("https://example.test/\x00")


async def test_request_url_bad_port_rejected():
    async with arequest.Session() as session:
        with pytest.raises(InvalidURL):
            await session.get("https://example.test:99999/")


# --- ws_connect validation -----------------------------------------------------


async def test_ws_connect_rejects_bad_urls():
    async with arequest.Session() as session:
        with pytest.raises(InvalidURL):
            await session.ws_connect("ws://example.test/\x00")
        with pytest.raises(InvalidURL):
            await session.ws_connect("ws://example.test:99999/")


# --- V5: proxy pool status masks credentials -----------------------------------


def test_proxy_pool_status_masks_credentials():
    pool = ProxyPool([f"http://user:{SECRET}@proxy1.example:8080"])
    status = pool.status()
    (url, healthy) = next(iter(status.items()))
    assert SECRET not in url
    assert healthy is True


def test_transport_error_is_request_error():
    # Sanity: translate_exception still maps unknown errors to TransportError.
    assert isinstance(translate_exception(KeyError("x")), TransportError)
