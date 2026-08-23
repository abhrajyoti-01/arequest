import random
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Union


@dataclass(frozen=True)
class RetryPolicy:
    total: int = 0
    backoff_factor: float = 0.25
    max_backoff: float = 30.0
    jitter: float = 0.1
    status_forcelist: frozenset[int] = field(
        default_factory=lambda: frozenset((429, 500, 502, 503, 504))
    )
    allowed_methods: frozenset[str] = field(
        default_factory=lambda: frozenset(("DELETE", "GET", "HEAD", "OPTIONS", "PUT"))
    )
    respect_retry_after_header: bool = True

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError("total retries cannot be negative")
        if self.backoff_factor < 0 or self.max_backoff < 0 or self.jitter < 0:
            raise ValueError("retry timing values cannot be negative")
        object.__setattr__(
            self,
            "allowed_methods",
            frozenset(method.upper() for method in self.allowed_methods),
        )
        object.__setattr__(self, "status_forcelist", frozenset(self.status_forcelist))

    @classmethod
    def from_value(
        cls,
        value: Union[int, "RetryPolicy", None],
        *,
        backoff_factor: float | None = None,
    ) -> "RetryPolicy":
        if isinstance(value, cls):
            if backoff_factor is None:
                return value
            return replace(value, backoff_factor=backoff_factor)
        total = 0 if value is None else int(value)
        kwargs = {"total": total}
        if backoff_factor is not None:
            kwargs["backoff_factor"] = backoff_factor
        return cls(**kwargs)

    def should_retry(
        self,
        method: str,
        retries_used: int,
        *,
        response: Any = None,
        error: Any = None,
    ) -> bool:
        if retries_used >= self.total:
            return False
        if method.upper() not in self.allowed_methods:
            return False
        if error is not None:
            return bool(getattr(error, "retryable", False))
        if response is not None:
            return int(getattr(response, "status_code", 0)) in self.status_forcelist
        return False

    def get_delay(self, retries_used: int, response: Any = None) -> float:
        if self.respect_retry_after_header and response is not None:
            retry_after = _retry_after_seconds(response)
            if retry_after is not None:
                return min(self.max_backoff, max(0.0, retry_after))
        delay = self.backoff_factor * (2 ** max(0, retries_used - 1))
        if delay and self.jitter:
            delay += random.uniform(0.0, self.jitter)
        return min(self.max_backoff, delay)


def _retry_after_seconds(response: Any) -> float | None:
    headers = getattr(response, "headers", {})
    value = headers.get("Retry-After") if headers is not None else None
    if not value:
        return None
    value = str(value).strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
