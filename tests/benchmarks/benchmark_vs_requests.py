"""Benchmark arequest against requests library (synchronous)."""

import asyncio
import argparse
import os
import time

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: requests not installed, skipping requests benchmarks")

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
        "library": "arequest (concurrent)",
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


def benchmark_requests_sequential(url: str, num_requests: int = 100) -> dict:
    """Benchmark requests library with sequential requests and session.

    Args:
        url: URL to request
        num_requests: Number of requests to make

    Returns:
        Dictionary with timing results
    """
    if not HAS_REQUESTS:
        return {"library": "requests", "error": "not installed"}

    start = time.perf_counter()
    errors = 0

    with requests.Session() as session:
        for _ in range(num_requests):
            try:
                response = session.get(url)
                _ = response.text
            except Exception:
                errors += 1

    elapsed = time.perf_counter() - start
    return {
        "library": "requests (sequential)",
        "requests": num_requests,
        "time": elapsed,
        "req_per_sec": num_requests / elapsed if elapsed > 0 else 0,
        "errors": errors,
    }


def benchmark_requests_no_session(url: str, num_requests: int = 100) -> dict:
    """Benchmark requests library without session (no connection reuse).

    Args:
        url: URL to request
        num_requests: Number of requests to make

    Returns:
        Dictionary with timing results
    """
    if not HAS_REQUESTS:
        return {"library": "requests", "error": "not installed"}

    start = time.perf_counter()
    errors = 0

    for _ in range(num_requests):
        try:
            response = requests.get(url)
            _ = response.text
        except Exception:
            errors += 1

    elapsed = time.perf_counter() - start
    return {
        "library": "requests (no session)",
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
        if HAS_REQUESTS:
            requests.get(test_url)
    except Exception as e:
        print(f"  Warmup error: {e}")
    print()

    results = []

    # Benchmark arequest concurrent (fastest mode)
    print("Benchmarking arequest (concurrent with connection pooling)...")
    arequest_concurrent_result = await benchmark_arequest_concurrent(test_url, num_requests)
    print(f"  Time: {arequest_concurrent_result['time']:.2f}s")
    print(f"  Requests/sec: {arequest_concurrent_result['req_per_sec']:.2f}")
    print(f"  Errors: {arequest_concurrent_result['errors']}")
    print()
    results.append(arequest_concurrent_result)

    # Benchmark arequest sequential
    print("Benchmarking arequest (sequential with connection reuse)...")
    arequest_seq_result = await benchmark_arequest_sequential(test_url, num_requests)
    print(f"  Time: {arequest_seq_result['time']:.2f}s")
    print(f"  Requests/sec: {arequest_seq_result['req_per_sec']:.2f}")
    print(f"  Errors: {arequest_seq_result['errors']}")
    print()
    results.append(arequest_seq_result)

    # Benchmark requests with session
    requests_session_result = None
    if HAS_REQUESTS:
        print("Benchmarking requests (sequential with session)...")
        requests_session_result = benchmark_requests_sequential(test_url, num_requests)
        if "error" not in requests_session_result:
            print(f"  Time: {requests_session_result['time']:.2f}s")
            print(f"  Requests/sec: {requests_session_result['req_per_sec']:.2f}")
            print(f"  Errors: {requests_session_result['errors']}")
            print()
            results.append(requests_session_result)

    # Benchmark requests without session
    requests_no_session_result = None
    if HAS_REQUESTS:
        print("Benchmarking requests (sequential without session)...")
        requests_no_session_result = benchmark_requests_no_session(test_url, num_requests)
        if "error" not in requests_no_session_result:
            print(f"  Time: {requests_no_session_result['time']:.2f}s")
            print(f"  Requests/sec: {requests_no_session_result['req_per_sec']:.2f}")
            print(f"  Errors: {requests_no_session_result['errors']}")
            print()
            results.append(requests_no_session_result)

    # Comparison
    if len(results) > 1:
        print("=" * 60)
        print("Comparison")
        print("=" * 60)
        
        fastest = max(results, key=lambda r: r["req_per_sec"])
        fastest_label = fastest["library"]

        for result in results:
            marker = "  <-- FASTEST" if result["library"] == fastest_label else ""
            print(f"{result['library']:35} {result['req_per_sec']:8.2f} req/s{marker}")
        
        print()
        
        if HAS_REQUESTS and requests_session_result:
            # Compare arequest concurrent vs requests with session
            areq_speed = arequest_concurrent_result['req_per_sec']
            req_speed = requests_session_result['req_per_sec']
            
            if areq_speed > 0 and req_speed > 0:
                ratio = areq_speed / req_speed
                speedup = (ratio - 1) * 100
                
                print(f"Performance vs requests (with session):")
                print(f"  arequest concurrent is {ratio:.2f}x faster ({speedup:+.1f}%)")
                print()
            
            # Compare arequest sequential vs requests with session
            areq_seq_speed = arequest_seq_result['req_per_sec']
            if areq_seq_speed > 0 and req_speed > 0:
                ratio = areq_seq_speed / req_speed
                speedup = (ratio - 1) * 100
                print(f"  arequest sequential is {ratio:.2f}x ({speedup:+.1f}%)")
                print()

        print("=" * 60)
        print()
        print("SUMMARY:")
        print(f"  Fastest configuration: {fastest_label}")
        print(f"  Peak performance: {fastest['req_per_sec']:.2f} requests/second")
        print()
        
        if HAS_REQUESTS:
            print("KEY INSIGHTS:")
            print("  • arequest concurrent mode leverages async I/O for maximum speed")
            print("  • Even arequest sequential mode benefits from optimized parsing")
            print("  • Connection pooling is critical for performance")
            print("  • For production use, prefer arequest concurrent mode")
        else:
            print("Install requests library to see comparison:")
            print("  pip install requests")


async def main():
    """Run benchmarks."""
    print("=" * 60)
    print("arequest vs requests Library Benchmark")
    print("=" * 60)
    print()

    parser = argparse.ArgumentParser(description="arequest vs requests benchmark")
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
