"""Basic example demonstrating arequest usage."""

import asyncio
import arequest


async def main():
    """Run basic examples."""
    print("Testing arequest basic functionality...\n")

    # Example 1: Simple GET request
    print("1. Making GET request to httpbin.org...")
    try:
        response = await arequest.get("https://httpbin.org/get")
        print(f"   Status: {response.status_code}")
        text = response.text
        print(f"   Response: {text[:100]}...")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n2. Making POST request with JSON...")
    try:
        response = await arequest.post(
            "https://httpbin.org/post",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        print(f"   Status: {response.status_code}")
        data = response.json()
        print(f"   Response JSON: {data.get('json', {})}")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n3. Using Session directly...")
    session = arequest.Session()
    try:
        response = await session.get("https://httpbin.org/get?test=value")
        print(f"   Status: {response.status_code}")
        print(f"   URL: {response.url}")
    except Exception as e:
        print(f"   Error: {e}")
    finally:
        await session.close()

    print("\n4. Using Session for connection pooling...")
    try:
        async with arequest.Session() as session:
            r1 = await session.get("https://httpbin.org/get?req=1")
            r2 = await session.get("https://httpbin.org/get?req=2")
            print(f"   Request 1 Status: {r1.status_code}")
            print(f"   Request 2 Status: {r2.status_code}")
            print("   (Connections are reused via connection pooling)")
    except Exception as e:
        print(f"   Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())

