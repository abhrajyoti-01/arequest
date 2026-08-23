"""Example: WebSocket connections with browser impersonation.

Requires network access. Connects to an echo endpoint with Chrome's
fingerprint and exchanges messages.
"""

import asyncio
import arequest


async def main():
    # Local echo round-trip against a public WS echo service
    async with arequest.Session(impersonate="chrome") as session:
        handle = await session.ws_connect("wss://ws.postman-echo.com/raw")
        async with handle as ws:
            await ws.send_json({"type": "ping", "n": 1})
            reply = await ws.recv_json()
            print("received:", reply)

            await ws.send_str("plain hello")
            print("received:", await ws.recv_str())


if __name__ == "__main__":
    asyncio.run(main())
