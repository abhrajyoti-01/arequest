import asyncio
import random
import time


class AsyncRateLimiter:
    """Token-bucket rate limiter with FIFO pacing under contention."""

    def __init__(
        self,
        rate: float,
        burst: int = 1,
        jitter: float = 0.0,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be greater than zero")
        if burst < 1:
            raise ValueError("burst must be at least one")
        if jitter < 0:
            raise ValueError("jitter cannot be negative")
        self.rate = float(rate)
        self.capacity = float(burst)
        self.jitter = float(jitter)
        self._tokens = float(burst)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()
        self._next_slot = time.monotonic()

    def _refill(self, now: float) -> None:
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated = now

    async def acquire(self) -> None:
        def _reserve() -> tuple[bool, float]:
            now = time.monotonic()
            self._refill(now)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True, 0.0
            deficit = 1.0 - self._tokens
            wait = deficit / self.rate
            slot = max(self._next_slot, now)
            self._next_slot = slot + (1.0 / self.rate)
            delay = max(0.0, (slot - now) + wait)
            if self.jitter:
                delay += random.uniform(0.0, self.jitter)
            return False, delay

        async with self._lock:
            immediate, delay = _reserve()

        if immediate:
            return
        await asyncio.sleep(delay)
        async with self._lock:
            self._refill(time.monotonic())
            self._tokens = max(0.0, self._tokens - 1.0)

    def __repr__(self) -> str:
        return (
            f"<AsyncRateLimiter rate={self.rate} burst={int(self.capacity)} "
            f"jitter={self.jitter}>"
        )
