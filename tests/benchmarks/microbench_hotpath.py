"""Micro-benchmark isolating arequest's pure-Python per-request overhead.

Uses an in-memory fake transport (no socket I/O) so the numbers reflect the
client hot path: limiter/slot bookkeeping, header resolution, Response
construction, etc. Run before/after a change to quantify CPU-side gains.
"""

import asyncio
import statistics
import time

from curl_cffi.requests import Cookies, Headers

import arequest


class RawResponse:
    def __init__(self, url="https://example.test/x"):
        self.status_code = 200
        self.content = b"ok"
        self.headers = Headers()
        self.url = url
        self.reason = "OK"
        self.elapsed = 0.0
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

    def __init__(self):
        self.cookies = Cookies()

    async def request(self, method, url, **kwargs):
        return RawResponse(url=url)

    async def close(self):
        pass


async def bench_request_path(n=500, fast=False):
    transport = FakeTransport()
    kwargs = {"connector_limit": 0, "connector_limit_per_host": 0} if fast else {}
    async with arequest.Session(transport=transport, **kwargs) as s:
        # Warm up
        for _ in range(20):
            await s.get("https://example.test/x")
        start = time.perf_counter()
        for i in range(n):
            await s.get(f"https://example.test/{i}")
        elapsed = time.perf_counter() - start
    return n / elapsed


async def bench_iter_fetch(n=500, concurrency=20):
    async with arequest.Session() as s:
        urls = [f"http://127.0.0.1:1/{i}" for i in range(n)]  # will fail fast (conn refused)
        start = time.perf_counter()
        count = 0
        async for _ in s.iter_fetch(urls, max_concurrency=concurrency, return_exceptions=True):
            count += 1
        elapsed = time.perf_counter() - start
    return count / elapsed if elapsed else 0.0, count


def main():
    samples = [asyncio.run(bench_request_path()) for _ in range(5)]
    print(f"request() hot path (default limits): {statistics.median(samples):.0f} req/s "
          f"(median of {[f'{s:.0f}' for s in samples]})")
    fast = [asyncio.run(bench_request_path(fast=True)) for _ in range(5)]
    print(f"request() hot path (no limits, fast path): {statistics.median(fast):.0f} req/s "
          f"(median of {[f'{s:.0f}' for s in fast]})")


if __name__ == "__main__":
    main()
