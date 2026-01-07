"""Optimized benchmark targeting 200+ req/s for arequest."""

import asyncio
from contextlib import asynccontextmanager
import os
import statistics
import time
from typing import Any

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

import arequest

_RESPONSE_BYTES = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: keep-alive\r\n"
    b"\r\n"
    b"OK"
)


@asynccontextmanager
async def run_local_server() -> Any:
    """Run a minimal local HTTP server for consistent benchmarks."""
    async def handle_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                try:
                    header = await reader.readuntil(b"\r\n\r\n")
                except asyncio.IncompleteReadError:
                    break

                if not header:
                    break

                header_lower = header.lower()
                close_after = b"connection: close" in header_lower

                # Drain body if Content-Length is provided (bench uses GET, so usually 0).
                content_length = 0
                for line in header.split(b"\r\n")[1:]:
                    if not line:
                        break
                    if line[:15].lower() == b"content-length":
                        parts = line.split(b":", 1)
                        if len(parts) == 2:
                            try:
                                content_length = int(parts[1].strip())
                            except ValueError:
                                content_length = 0
                        break

                if content_length > 0:
                    try:
                        await reader.readexactly(content_length)
                    except asyncio.IncompleteReadError:
                        break

                writer.write(_RESPONSE_BYTES)
                await writer.drain()

                if close_after:
                    break
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    sockets = server.sockets or []
    if not sockets:
        server.close()
        await server.wait_closed()
        raise RuntimeError("Failed to start local benchmark server")

    host, port = sockets[0].getsockname()[:2]
    url = f"http://{host}:{port}/"

    try:
        yield url
    finally:
        server.close()
        await server.wait_closed()


async def benchmark_arequest_optimized(
    url: str, num_requests: int = 2000, concurrency: int = 200
) -> dict[str, Any]:
    """Benchmark arequest with optimized settings for 200+ req/s.

    Args:
        url: URL to request
        num_requests: Total requests
        concurrency: Concurrent requests

    Returns:
        Performance metrics
    """
    print(f"\nBenchmarking arequest (optimized for 200+ req/s)...")
    print(f"  Requests: {num_requests}, Concurrency: {concurrency}")

    start = time.perf_counter()
    errors = 0
    latencies = []

    pipeline_env = os.environ.get("AREQUEST_BENCH_PIPELINE", "0")
    try:
        pipeline_max = max(0, int(pipeline_env))
    except ValueError:
        pipeline_max = 0
    if pipeline_max > concurrency:
        pipeline_max = concurrency

    # Use session with optional pipelining for maximum performance
    try:
        session_cm = arequest.Session(pipeline_max=pipeline_max) if pipeline_max > 1 else arequest.Session()
        pipeline_enabled = pipeline_max > 1
    except TypeError:
        session_cm = arequest.Session()
        pipeline_enabled = False

    async with session_cm as session:
        if pipeline_max > 1 and not pipeline_enabled:
            print("  Pipeline requested but not supported by this Session implementation.")
        elif pipeline_enabled:
            print(f"  Pipeline: {pipeline_max} requests/connection")
        semaphore = asyncio.Semaphore(concurrency)

        async def make_request():
            nonlocal errors
            async with semaphore:
                req_start = time.perf_counter()
                try:
                    resp = await session.get(url)
                    # Read response (use content property - synchronous)
                    _ = resp.content
                    latencies.append(time.perf_counter() - req_start)
                except Exception:
                    errors += 1

        tasks = [make_request() for _ in range(num_requests)]
        await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.perf_counter() - start
    req_per_sec = num_requests / elapsed if elapsed > 0 else 0

    if latencies:
        avg = statistics.mean(latencies) * 1000
        p50 = statistics.median(latencies) * 1000
        p95 = (
            statistics.quantiles(latencies, n=20)[18]
            if len(latencies) > 20
            else max(latencies) * 1000
        )
    else:
        avg = p50 = p95 = 0

    result = {
        "library": "arequest (optimized)",
        "req_per_sec": req_per_sec,
        "time": elapsed,
        "avg_latency_ms": avg,
        "p50_ms": p50,
        "p95_ms": p95,
        "errors": errors,
    }

    print(f"  Time: {elapsed:.2f}s")
    print(f"  Requests/sec: {req_per_sec:.2f}")
    print(f"  Avg latency: {avg:.2f}ms")
    print(f"  P50 latency: {p50:.2f}ms")
    print(f"  P95 latency: {p95:.2f}ms")
    print(f"  Errors: {errors}")

    return result


async def benchmark_aiohttp_optimized(
    url: str, num_requests: int = 2000, concurrency: int = 200
) -> dict[str, Any]:
    """Benchmark aiohttp for comparison."""
    if not HAS_AIOHTTP:
        return {"library": "aiohttp", "req_per_sec": 0, "errors": num_requests}

    print(f"\nBenchmarking aiohttp...")
    print(f"  Requests: {num_requests}, Concurrency: {concurrency}")

    start = time.perf_counter()
    errors = 0
    latencies = []

    async with aiohttp.ClientSession() as session:
        semaphore = asyncio.Semaphore(concurrency)

        async def make_request():
            nonlocal errors
            async with semaphore:
                req_start = time.perf_counter()
                try:
                    async with session.get(url) as resp:
                        await resp.text()
                    latencies.append(time.perf_counter() - req_start)
                except Exception:
                    errors += 1

        tasks = [make_request() for _ in range(num_requests)]
        await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.perf_counter() - start
    req_per_sec = num_requests / elapsed if elapsed > 0 else 0

    if latencies:
        avg = statistics.mean(latencies) * 1000
        p50 = statistics.median(latencies) * 1000
        p95 = (
            statistics.quantiles(latencies, n=20)[18]
            if len(latencies) > 20
            else max(latencies) * 1000
        )
    else:
        avg = p50 = p95 = 0

    result = {
        "library": "aiohttp",
        "req_per_sec": req_per_sec,
        "time": elapsed,
        "avg_latency_ms": avg,
        "p50_ms": p50,
        "p95_ms": p95,
        "errors": errors,
    }

    print(f"  Time: {elapsed:.2f}s")
    print(f"  Requests/sec: {req_per_sec:.2f}")
    print(f"  Avg latency: {avg:.2f}ms")
    print(f"  P50 latency: {p50:.2f}ms")
    print(f"  P95 latency: {p95:.2f}ms")
    print(f"  Errors: {errors}")

    return result


async def run_benchmarks(test_url: str, num_requests: int, concurrency: int) -> None:
    """Run optimized benchmarks targeting 200+ req/s."""
    print(f"\nConfiguration:")
    print(f"  URL: {test_url}")
    print(f"  Total requests: {num_requests}")
    print(f"  Concurrency: {concurrency}")

    # Warmup
    print("\nWarming up...")
    try:
        await arequest.get(test_url)
    except Exception:
        pass

    results = []

    # Benchmark arequest
    arequest_result = await benchmark_arequest_optimized(
        test_url, num_requests, concurrency
    )
    results.append(arequest_result)

    # Benchmark aiohttp
    if HAS_AIOHTTP:
        aiohttp_result = await benchmark_aiohttp_optimized(
            test_url, num_requests, concurrency
        )
        results.append(aiohttp_result)

    # Summary
    print("\n" + "=" * 80)
    print("PERFORMANCE SUMMARY")
    print("=" * 80)

    results_sorted = sorted(results, key=lambda x: x["req_per_sec"], reverse=True)

    print(
        f"\n{'Library':<20} {'Req/s':<12} {'Avg(ms)':<12} {'P50(ms)':<12} "
        f"{'P95(ms)':<12} {'Status':<15}"
    )
    print("-" * 80)
    for r in results_sorted:
        status = "[TOP]" if r == results_sorted[0] else ""
        print(
            f"{r['library']:<20} {r['req_per_sec']:>10.2f}  "
            f"{r['avg_latency_ms']:>10.2f}  {r['p50_ms']:>10.2f}  "
            f"{r['p95_ms']:>10.2f}  {status:<15}"
        )

    # Check if target achieved
    arequest_rps = next(
        (r["req_per_sec"] for r in results if "arequest" in r["library"]), 0
    )
    print("\n" + "=" * 80)
    print("TARGET: 200+ req/s")
    print("=" * 80)
    if arequest_rps >= 200:
        print(f"\n[SUCCESS] arequest achieved {arequest_rps:.2f} req/s - target met.")
    else:
        print(
            f"\narequest: {arequest_rps:.2f} req/s (need {200 - arequest_rps:.2f} more for target)"
        )
        if arequest_rps > 0:
            improvement_needed = (200 / arequest_rps) - 1
            print(f"Need {improvement_needed:.1%} improvement to reach 200 req/s")

    print("\n" + "=" * 80)


async def main() -> None:
    """Run optimized benchmarks targeting 200+ req/s."""
    print("=" * 80)
    print("OPTIMIZED BENCHMARK - Targeting 200+ req/s")
    print("=" * 80)

    bench_url = os.environ.get("AREQUEST_BENCH_URL")
    num_requests = int(os.environ.get("AREQUEST_BENCH_REQUESTS", "2000"))
    concurrency = int(os.environ.get("AREQUEST_BENCH_CONCURRENCY", "200"))

    if bench_url:
        print("\nUsing AREQUEST_BENCH_URL override.")
        await run_benchmarks(bench_url, num_requests, concurrency)
        return

    print("\nUsing local benchmark server (set AREQUEST_BENCH_URL to override).")
    async with run_local_server() as local_url:
        await run_benchmarks(local_url, num_requests, concurrency)


if __name__ == "__main__":
    asyncio.run(main())
