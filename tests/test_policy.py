from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from arequest import ImpersonationError, RetryPolicy, Timeout, available_profiles
from arequest.models import normalize_timeout
from arequest.profiles import resolve_impersonate
from arequest.transport import normalize_http_version


class Response:
    def __init__(self, status_code=503, retry_after=None):
        self.status_code = status_code
        self.headers = {} if retry_after is None else {"Retry-After": retry_after}


def test_timeout_normalization():
    assert normalize_timeout(3) == 3.0
    assert normalize_timeout((1, 2)) == (1.0, 2.0)
    assert normalize_timeout(Timeout(connect=1, read=2)) == (1.0, 2.0)
    assert normalize_timeout(None) is None


@pytest.mark.parametrize("value", [-1, (-1, 2), (1, -2)])
def test_timeout_rejects_negative_values(value):
    with pytest.raises(ValueError):
        normalize_timeout(value)


def test_retry_policy_is_idempotent_by_default():
    policy = RetryPolicy(total=2, backoff_factor=0, jitter=0)
    assert policy.should_retry("GET", 0, response=Response())
    assert not policy.should_retry("POST", 0, response=Response())
    assert not policy.should_retry("GET", 2, response=Response())
    assert not policy.should_retry("GET", 0, response=Response(404))


def test_retry_after_delta_and_date():
    policy = RetryPolicy(total=1, max_backoff=60, jitter=0)
    assert policy.get_delay(1, Response(retry_after="4")) == 4
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=5))
    assert 0 <= policy.get_delay(1, Response(retry_after=future)) <= 6


def test_profile_resolution_uses_installed_backend_profiles():
    assert resolve_impersonate(True) == "chrome"
    assert resolve_impersonate("chrome-latest") == "chrome"
    assert resolve_impersonate(False) is None
    assert "chrome" in available_profiles()
    with pytest.raises(ImpersonationError):
        resolve_impersonate("browser_that_does_not_exist")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("auto", None), ("h1", "v1"), ("http/2", "v2"), ("h3", "v3")],
)
def test_http_version_aliases(value, expected):
    assert normalize_http_version(value) == expected


def test_http_version_rejects_unknown_value():
    with pytest.raises(ValueError):
        normalize_http_version("http/9")
