"""Sequential benchmark: requests vs arequest (external URL by default)."""

import asyncio
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading
import time
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import arequest


class _FastHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


@contextmanager
def run_local_server() -> Any:
    """Run a lightweight local HTTP server for low-latency benchmarks."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FastHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def benchmark_requests(url: str, num_requests: int) -> dict[str, Any]:
    """Run sequential requests using requests.Session."""
    if not HAS_REQUESTS:
        return {"library": "requests", "error": "not installed", "requests": num_requests}

    errors = 0

    with requests.Session() as session:
        try:
            warmup = session.get(url, timeout=10)
            _ = warmup.text
        except Exception:
            pass

        start = time.perf_counter()
        for _ in range(num_requests):
            try:
                resp = session.get(url, timeout=10)
                _ = resp.text
            except Exception:
                errors += 1

    elapsed = time.perf_counter() - start
    return {
        "library": "requests",
        "requests": num_requests,
        "time": elapsed,
        "req_per_sec": num_requests / elapsed if elapsed > 0 else 0,
        "errors": errors,
    }


async def benchmark_arequest(url: str, num_requests: int) -> dict[str, Any]:
    """Run sequential requests using arequest.Session."""
    errors = 0

    async with arequest.Session() as session:
        try:
            warmup = await session.get(url)
            _ = warmup.text
        except Exception:
            pass

        start = time.perf_counter()
        for _ in range(num_requests):
            try:
                resp = await session.get(url)
                _ = resp.text
            except Exception:
                errors += 1

    elapsed = time.perf_counter() - start
    return {
        "library": "arequest",
        "requests": num_requests,
        "time": elapsed,
        "req_per_sec": num_requests / elapsed if elapsed > 0 else 0,
        "errors": errors,
    }


async def run_benchmark(url: str, num_requests: int) -> None:
    """Run sequential comparison."""
    print("=" * 60)
    print("Sequential Benchmark: requests vs arequest")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Requests: {num_requests}")
    print()

    results = []

    requests_result = benchmark_requests(url, num_requests)
    results.append(requests_result)
    if "error" in requests_result:
        print("requests: not installed (pip install requests)")
    else:
        print(f"requests:  {requests_result['time']:.2f}s  "
              f"{requests_result['req_per_sec']:.2f} req/s  "
              f"errors={requests_result['errors']}")

    arequest_result = await benchmark_arequest(url, num_requests)
    results.append(arequest_result)
    print(f"arequest:  {arequest_result['time']:.2f}s  "
          f"{arequest_result['req_per_sec']:.2f} req/s  "
          f"errors={arequest_result['errors']}")

    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        winner = max(valid_results, key=lambda r: r["req_per_sec"])
        print()
        print(f"Fastest: {winner['library']} ({winner['req_per_sec']:.2f} req/s)")

    print()
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Sequential requests vs arequest benchmark")
    parser.add_argument("--url", help="Target URL (overrides AREQUEST_BENCH_URL)")
    parser.add_argument(
        "--requests",
        type=int,
        default=int(os.environ.get("AREQUEST_BENCH_REQUESTS", "10")),
        help="Number of requests to make (default: 10 or AREQUEST_BENCH_REQUESTS)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use a local in-process HTTP server for low-latency testing",
    )
    return parser.parse_args()


async def main() -> None:
    """Run sequential comparison."""
    args = parse_args()
    env_url = os.environ.get("AREQUEST_BENCH_URL")
    url = args.url or env_url or "https://httpbin.org/get"

    if args.local:
        print("Using local benchmark server (--local).")
        with run_local_server() as local_url:
            await run_benchmark(local_url, args.requests)
        return

    if args.url:
        print("Using --url override.")
    elif env_url:
        print("Using AREQUEST_BENCH_URL override.")
    else:
        print("Using default URL (set AREQUEST_BENCH_URL or --url to override).")

    await run_benchmark(url, args.requests)


if __name__ == "__main__":
    asyncio.run(main())
