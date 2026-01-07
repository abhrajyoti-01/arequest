"""Example demonstrating Session usage with connection pooling."""

import asyncio
import arequest


async def main():
    """Run session examples."""
    print("Testing arequest Session functionality...\n")

    # Example 1: Using session context manager
    print("1. Using session context manager...")
    async with arequest.Session() as session:
        # Multiple requests to same host - connections will be reused
        response1 = await session.get("https://httpbin.org/get?req=1")
        print(f"   Request 1 Status: {response1.status_code}")

        response2 = await session.get("https://httpbin.org/get?req=2")
        print(f"   Request 2 Status: {response2.status_code}")

        response3 = await session.post(
            "https://httpbin.org/post",
            json={"test": "data"},
        )
        print(f"   POST Status: {response3.status_code}")
        data = response3.json()
        print(f"   POST Response: {data.get('json', {})}")

    print("\n2. Using session with default headers...")
    async with arequest.Session(headers={"User-Agent": "arequest/0.1.0"}) as session:
        response = await session.get("https://httpbin.org/headers")
        headers_data = response.json()
        print(f"   User-Agent sent: {headers_data.get('headers', {}).get('User-Agent', 'N/A')}")

    print("\n3. Manual session management...")
    session = arequest.Session()
    try:
        response = await session.get("https://httpbin.org/get")
        print(f"   Status: {response.status_code}")
    finally:
        await session.close()
        print("   Session closed")


if __name__ == "__main__":
    asyncio.run(main())

