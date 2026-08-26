import random
import time
from collections.abc import Iterable
from urllib.parse import urlsplit

from .exceptions import ProxyError, strip_credentials

_STRATEGIES = frozenset(("round_robin", "random", "failover"))


class _ProxyState:
    __slots__ = ("url", "failed_until", "failures")

    def __init__(self, url: str) -> None:
        self.url = url
        self.failed_until = 0.0
        self.failures = 0


class ProxyPool:
    """Rotating pool of proxy URLs with failure cooldowns.

    Args:
        proxies: Proxy URLs (``http://``, ``https://``, ``socks4://``,
            ``socks5://`` ...).
        strategy: ``"round_robin"`` cycles through proxies in order,
            ``"random"`` picks uniformly, ``"failover"`` prefers the first
            healthy proxy and only moves on when it fails.
        cooldown: Seconds a proxy is skipped after a failure.
    """

    def __init__(
        self,
        proxies: Iterable[str],
        *,
        strategy: str = "round_robin",
        cooldown: float = 300.0,
    ) -> None:
        if strategy not in _STRATEGIES:
            supported = ", ".join(sorted(_STRATEGIES))
            raise ValueError(f"unknown proxy strategy {strategy!r}; expected one of: {supported}")
        if cooldown < 0:
            raise ValueError("cooldown cannot be negative")

        unique: list[str] = []
        seen = set()
        for proxy in proxies:
            url = str(proxy)
            parts = urlsplit(url)
            if parts.scheme.lower() not in ("http", "https", "socks4", "socks4a", "socks5", "socks5h") or not parts.hostname:
                raise ValueError(f"invalid proxy URL: {url!r}")
            if url not in seen:
                seen.add(url)
                unique.append(url)
        if not unique:
            raise ValueError("proxy pool cannot be empty")

        self.strategy = strategy
        self.cooldown = float(cooldown)
        self._states = [_ProxyState(url) for url in unique]
        self._by_url = {state.url: state for state in self._states}
        self._index = 0

    def acquire(self) -> str:
        """Return the next healthy proxy URL, or raise ProxyError."""
        now = time.monotonic()
        if self.strategy == "random":
            healthy = [s for s in self._states if s.failed_until <= now]
            if not healthy:
                raise ProxyError("no healthy proxies available in pool")
            return random.choice(healthy).url

        total = len(self._states)
        fallback: str = ""
        for offset in range(total):
            state = self._states[(self._index + offset) % total]
            if state.failed_until > now:
                continue
            if not fallback:
                fallback = state.url
            if self.strategy == "round_robin":
                self._index = (self._index + offset + 1) % total
                return state.url
        if not fallback:
            raise ProxyError("no healthy proxies available in pool")
        return fallback

    def report_failure(self, proxy: str) -> None:
        """Put a proxy into cooldown after a connection failure."""
        state = self._by_url.get(proxy)
        if state is None:
            return
        state.failures += 1
        state.failed_until = time.monotonic() + self.cooldown

    def report_success(self, proxy: str) -> None:
        """Clear failure state for a proxy."""
        state = self._by_url.get(proxy)
        if state is None:
            return
        state.failures = 0
        state.failed_until = 0.0

    def status(self) -> dict[str, bool]:
        """Map each proxy URL to whether it is currently healthy.

        URLs are returned with any ``user:password`` userinfo masked so the
        result is safe to log.
        """
        now = time.monotonic()
        return {
            strip_credentials(state.url): state.failed_until <= now
            for state in self._states
        }

    def __len__(self) -> int:
        return len(self._states)

    def __repr__(self) -> str:
        return f"<ProxyPool strategy={self.strategy!r} size={len(self._states)}>"
