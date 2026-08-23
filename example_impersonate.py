"""Example: browser impersonation with real TLS/HTTP2 fingerprints.

Requires network access. Verifies fingerprints against tls.peet.ws.
"""

import asyncio
import arequest


async def main():
    # 1. Session-wide impersonation (latest Chrome by default)
    async with arequest.Session(impersonate="chrome") as session:
        r = await session.get("https://tls.peet.ws/api/all")
        data = r.json()
        print("=== impersonate='chrome' ===")
        print("HTTP version:   ", data["http_version"])
        print("JA3 hash:       ", data["tls"]["ja3_hash"])
        print("JA4:            ", data["tls"]["ja4"])
        print("Akamai h2 hash: ", data["http2"]["akamai_fingerprint_hash"])
        print("User-Agent:     ", data["user_agent"])

    # 2. Per-request profile switch
    r = await arequest.get(
        "https://tls.peet.ws/api/all",
        impersonate="safari_ios",
    )
    print("\n=== impersonate='safari_ios' ===")
    print("User-Agent:     ", r.json()["user_agent"])

    # 3. List every profile available in the installed engine
    print("\nAvailable profiles:")
    print(", ".join(arequest.available_profiles()))


if __name__ == "__main__":
    asyncio.run(main())
