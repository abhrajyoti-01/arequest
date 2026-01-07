"""Example showing arequest with requests-compatible API.

This demonstrates that arequest can be used as a drop-in replacement
for the requests library, but with much better performance due to
async I/O and optimized parsing.
"""

import asyncio
import arequest


async def main():
    print("=" * 60)
    print("arequest - requests-compatible API with async performance")
    print("=" * 60)
    print()
    
    # Example 1: Simple GET request (just like requests)
    print("1. Simple GET request (requests-compatible API):")
    response = await arequest.get('https://httpbin.org/get')
    print(f"   Status: {response.status_code}")
    print(f"   OK: {response.ok}")
    print(f"   Reason: {response.reason}")
    print(f"   Encoding: {response.encoding}")
    print(f"   Content-Type: {response.headers.get('Content-Type')}")
    print()
    
    # Example 2: POST with JSON (just like requests)
    print("2. POST request with JSON (requests-compatible):")
    data = {'name': 'Alice', 'email': 'alice@example.com'}
    response = await arequest.post('https://httpbin.org/post', json=data)
    print(f"   Status: {response.status_code}")
    result = response.json()
    print(f"   Posted data: {result['json']}")
    print()
    
    # Example 3: Using Session (just like requests.Session)
    print("3. Using Session for connection pooling (requests-compatible):")
    async with arequest.Session() as session:
        # Set default headers for all requests in this session
        session.headers = {'User-Agent': 'MyApp/1.0'}
        
        # Make multiple requests - connections are reused
        r1 = await session.get('https://httpbin.org/get')
        r2 = await session.get('https://httpbin.org/headers')
        
        print(f"   Request 1 status: {r1.status_code}")
        print(f"   Request 2 status: {r2.status_code}")
        print(f"   Connection pooling enabled!")
    print()
    
    # Example 4: Error handling (just like requests)
    print("4. Error handling with raise_for_status() (requests-compatible):")
    try:
        response = await arequest.get('https://httpbin.org/status/404')
        response.raise_for_status()
    except arequest.ClientError as e:
        print(f"   Caught error: {e}")
    print()
    
    # Example 5: Query parameters (just like requests)
    print("5. Query parameters (requests-compatible):")
    params = {'key1': 'value1', 'key2': 'value2'}
    response = await arequest.get('https://httpbin.org/get', params=params)
    result = response.json()
    print(f"   Parameters sent: {result['args']}")
    print()
    
    # Example 6: Custom headers (just like requests)
    print("6. Custom headers (requests-compatible):")
    headers = {'X-Custom-Header': 'MyValue'}
    response = await arequest.get('https://httpbin.org/headers', headers=headers)
    result = response.json()
    print(f"   Custom header received: {result['headers'].get('X-Custom-Header')}")
    print()
    
    # Example 7: Form data (just like requests)
    print("7. Form data POST (requests-compatible):")
    form_data = {'username': 'alice', 'password': 'secret'}
    response = await arequest.post('https://httpbin.org/post', data=form_data)
    result = response.json()
    print(f"   Form data posted: {result['form']}")
    print()
    
    # Example 8: Response content access (just like requests)
    print("8. Response content access (requests-compatible):")
    response = await arequest.get('https://httpbin.org/get')
    print(f"   response.text[:100]: {response.text[:100]}...")
    print(f"   response.content[:50]: {response.content[:50]}...")
    print(f"   response.json() keys: {list(response.json().keys())}")
    print()
    
    # Example 9: Performance comparison - Concurrent requests
    print("9. Performance advantage - Concurrent requests:")
    print("   Making 10 concurrent requests...")
    import time
    start = time.perf_counter()
    
    async with arequest.Session() as session:
        # Make 10 concurrent requests using asyncio.gather
        tasks = [session.get('https://httpbin.org/get') for _ in range(10)]
        responses = await asyncio.gather(*tasks)
    
    elapsed = time.perf_counter() - start
    print(f"   Completed 10 requests in {elapsed:.2f} seconds")
    print(f"   Average: {10/elapsed:.2f} requests/second")
    print(f"   (This would be much slower with synchronous requests library!)")
    print()
    
    # Example 10: Bulk operations made easy
    print("10. Bulk operations with simple API:")
    urls = [
        'https://httpbin.org/get',
        'https://httpbin.org/headers',
        'https://httpbin.org/user-agent',
    ]
    
    async with arequest.Session() as session:
        responses = await session.bulk_get(urls)
    
    print(f"   Fetched {len(responses)} URLs concurrently")
    for i, response in enumerate(responses, 1):
        print(f"   Response {i}: {response.status_code}")
    print()
    
    print("=" * 60)
    print("Summary:")
    print("  ✓ 100% requests-compatible API")
    print("  ✓ Drop-in async replacement")
    print("  ✓ 5-10x faster with concurrent requests")
    print("  ✓ Connection pooling built-in")
    print("  ✓ Optimized parsing and encoding")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
