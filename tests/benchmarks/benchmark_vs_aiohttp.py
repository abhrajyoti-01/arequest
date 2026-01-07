"""Benchmark arequest against aiohttp (external URL by default)."""

import asyncio
import argparse
import os
import time

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    print("Warning: aiohttp not installed, skipping aiohttp benchmarks")

import arequest

DEFAULT_URL = "https://httpbin.org/get"


async def benchmark_arequest_concurrent(url: str, num_requests: int = 100) -> dict:
    """Benchmark arequest concurrent GET requests with a pooled session.

    Args:
        url: URL to request
        num_requests: Number of requests to make

    Returns:
        Dictionary with timing results
    """
    start = time.perf_counter()
    errors = 0

    # Use Session for connection pooling
    async with arequest.Session() as session:
        tasks = [session.get(url) for _ in range(num_requests)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception):
                errors += 1
            else:
                _ = resp.text  # Read response

    elapsed = time.perf_counter() - start
    return {
        "library": "arequest",
        "requests": num_requests,
        "time": elapsed,
        "req_per_sec": num_requests / elapsed if elapsed > 0 else 0,
        "errors": errors,
    }


async def benchmark_aiohttp_concurrent(url: str, num_requests: int = 100) -> dict:
    """Benchmark aiohttp concurrent GET requests.

    Args:
        url: URL to request
        num_requests: Number of requests to make

    Returns:
        Dictionary with timing results
    """
    if not HAS_AIOHTTP:
        return {"library": "aiohttp", "error": "not installed"}

    start = time.perf_counter()
    errors = 0

    async with aiohttp.ClientSession() as session:
        tasks = [session.get(url) for _ in range(num_requests)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception):
                errors += 1
            else:
                async with resp:
                    await resp.text()  # Read response

    elapsed = time.perf_counter() - start
    return {
        "library": "aiohttp",
        "requests": num_requests,
        "time": elapsed,
        "req_per_sec": num_requests / elapsed if elapsed > 0 else 0,
        "errors": errors,
    }


async def benchmark_arequest_sequential(url: str, num_requests: int = 100) -> dict:
    """Benchmark arequest with sequential requests (connection reuse).

    Args:
        url: URL to request
        num_requests: Number of requests to make

    Returns:
        Dictionary with timing results
    """
    start = time.perf_counter()
    errors = 0

    async with arequest.Session() as session:
        for _ in range(num_requests):
            try:
                response = await session.get(url)
                _ = response.text
            except Exception:
                errors += 1

    elapsed = time.perf_counter() - start
    return {
        "library": "arequest (sequential)",
        "requests": num_requests,
        "time": elapsed,
        "req_per_sec": num_requests / elapsed if elapsed > 0 else 0,
        "errors": errors,
    }


async def benchmark_arequest_bulk(url: str, num_requests: int = 100) -> dict:
    """Benchmark arequest with bulk_get (simple API, concurrent execution).

    Args:
        url: URL to request
        num_requests: Number of requests to make

    Returns:
        Dictionary with timing results
    """
    start = time.perf_counter()
    errors = 0

    async with arequest.Session() as session:
        # Use bulk_get for simple concurrent requests
        urls = [url] * num_requests
        try:
            responses = await session.bulk_get(urls)
            for resp in responses:
                if isinstance(resp, Exception):
                    errors += 1
                else:
                    _ = resp.text
        except Exception:
            errors += num_requests

    elapsed = time.perf_counter() - start
    return {
        "library": "arequest (bulk_get)",
        "requests": num_requests,
        "time": elapsed,
        "req_per_sec": num_requests / elapsed if elapsed > 0 else 0,
        "errors": errors,
    }


async def run_benchmarks(test_url: str, num_requests: int) -> None:
    """Run benchmarks."""
    print(f"Test URL: {test_url}")
    print(f"Number of requests: {num_requests}")
    print()

    # Warmup
    print("Warming up...")
    try:
        await arequest.get(test_url)
        if HAS_AIOHTTP:
            async with aiohttp.ClientSession() as s:
                async with s.get(test_url) as r:
                    await r.text()
    except Exception as e:
        print(f"  Warmup error: {e}")
    print()

    # Benchmark arequest sequential (connection reuse)
    print("Benchmarking arequest (sequential with connection reuse)...")
    arequest_seq_result = await benchmark_arequest_sequential(test_url, num_requests)
    print(f"  Time: {arequest_seq_result['time']:.2f}s")
    print(f"  Requests/sec: {arequest_seq_result['req_per_sec']:.2f}")
    print(f"  Errors: {arequest_seq_result['errors']}")
    print()

    # Benchmark arequest bulk_get (simple API, concurrent execution)
    print("Benchmarking arequest (bulk_get - simple concurrent API)...")
    arequest_bulk_result = await benchmark_arequest_bulk(test_url, num_requests)
    print(f"  Time: {arequest_bulk_result['time']:.2f}s")
    print(f"  Requests/sec: {arequest_bulk_result['req_per_sec']:.2f}")
    print(f"  Errors: {arequest_bulk_result['errors']}")
    print()

    # Benchmark arequest concurrent
    print("Benchmarking arequest (concurrent with asyncio.gather)...")
    arequest_result = await benchmark_arequest_concurrent(test_url, num_requests)
    print(f"  Time: {arequest_result['time']:.2f}s")
    print(f"  Requests/sec: {arequest_result['req_per_sec']:.2f}")
    print(f"  Errors: {arequest_result['errors']}")
    print()

    arequest_runs = [
        arequest_seq_result,
        arequest_bulk_result,
        arequest_result,
    ]
    fastest_arequest = max(arequest_runs, key=lambda r: r["req_per_sec"])
    fastest_arequest_label = fastest_arequest["library"]

    # Benchmark aiohttp
    aiohttp_result = None
    if HAS_AIOHTTP:
        print("Benchmarking aiohttp (concurrent requests)...")
        aiohttp_result = await benchmark_aiohttp_concurrent(test_url, num_requests)
        if "error" not in aiohttp_result:
            print(f"  Time: {aiohttp_result['time']:.2f}s")
            print(f"  Requests/sec: {aiohttp_result['req_per_sec']:.2f}")
            print(f"  Errors: {aiohttp_result['errors']}")
            print()

            # Comparison
            print("=" * 60)
            print("Comparison")
            print("=" * 60)
            overall_runs = arequest_runs + [aiohttp_result]
            fastest_overall = max(overall_runs, key=lambda r: r["req_per_sec"])
            fastest_overall_label = fastest_overall["library"]

            def tag_for(label: str) -> str:
                tags = []
                if label == fastest_arequest_label:
                    tags.append("Fastest arequest")
                if label == fastest_overall_label:
                    tags.append("Fastest overall")
                return f"  <-- {', '.join(tags)}" if tags else ""

            print(f"arequest (sequential):  {arequest_seq_result['req_per_sec']:.2f} req/s{tag_for('arequest (sequential)')}")
            print(f"arequest (bulk_get):    {arequest_bulk_result['req_per_sec']:.2f} req/s{tag_for('arequest (bulk_get)')}")
            print(f"arequest (concurrent):  {arequest_result['req_per_sec']:.2f} req/s{tag_for('arequest')}")
            print(f"aiohttp (concurrent):   {aiohttp_result['req_per_sec']:.2f} req/s{tag_for('aiohttp')}")
            print()

            if arequest_result['req_per_sec'] > 0 and aiohttp_result['req_per_sec'] > 0:
                ratio = arequest_result['req_per_sec'] / aiohttp_result['req_per_sec']
                if ratio >= 1.0:
                    print(f"[OK] arequest is {ratio:.1%} of aiohttp performance.")
                elif ratio >= 0.9:
                    print(f"[OK] arequest is {ratio:.1%} of aiohttp performance")
                else:
                    print(f"[WARN] arequest is {ratio:.1%} of aiohttp performance")
        else:
            print(f"  Error: {aiohttp_result['error']}")
    else:
        print("Skipping aiohttp benchmark (not installed)")
        print("Install with: pip install aiohttp")

    fastest_overall_label = fastest_arequest_label
    if aiohttp_result and "error" not in aiohttp_result:
        overall_runs = arequest_runs + [aiohttp_result]
        fastest_overall = max(overall_runs, key=lambda r: r["req_per_sec"])
        fastest_overall_label = fastest_overall["library"]

    print()
    print("=" * 60)
    print()
    print(f"TIP: Fastest arequest mode in this run: {fastest_arequest_label}.")
    print(f"TIP: Fastest overall in this run: {fastest_overall_label}.")
    print("TIP: For real network latency, concurrent requests usually outperform sequential calls.")


async def main():
    """Run benchmarks."""
    print("=" * 60)
    print("arequest vs aiohttp Benchmark")
    print("=" * 60)
    print()

    parser = argparse.ArgumentParser(description="arequest vs aiohttp benchmark")
    parser.add_argument("url", nargs="?", help="Target URL (overrides AREQUEST_BENCH_URL)")
    parser.add_argument(
        "--requests",
        type=int,
        default=int(os.environ.get("AREQUEST_BENCH_REQUESTS", "50")),
        help="Number of requests to make (default: 50 or AREQUEST_BENCH_REQUESTS)",
    )
    args = parser.parse_args()

    env_url = os.environ.get("AREQUEST_BENCH_URL")
    bench_url = args.url or env_url or DEFAULT_URL

    if args.url:
        print("Using command-line URL override.")
    elif env_url:
        print("Using AREQUEST_BENCH_URL override.")
    else:
        print("Using default URL (set AREQUEST_BENCH_URL or pass a URL to override).")

    await run_benchmarks(bench_url, args.requests)


if __name__ == "__main__":
    asyncio.run(main())
