import asyncio
import time
from typing import Optional


class AsyncRateLimiter:
    def __init__(self, rate: float, burst: int = 1) -> None:
        if rate <= 0:
            raise ValueError("rate must be greater than zero")
        if burst < 1:
            raise ValueError("burst must be at least one")
        self.rate = float(rate)
        self.capacity = float(burst)
        self._tokens = float(burst)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            wait_for: Optional[float] = None
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_for = (1.0 - self._tokens) / self.rate
            await asyncio.sleep(wait_for)
