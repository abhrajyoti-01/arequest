from typing import get_args

from .exceptions import ImpersonationError

try:
    from curl_cffi.requests.impersonate import BrowserTypeLiteral

    _SUPPORTED = frozenset(get_args(BrowserTypeLiteral))
except ImportError:
    _SUPPORTED = frozenset()

_ALIASES = {
    "latest": "chrome",
    "chrome_latest": "chrome",
    "chrome_desktop": "chrome",
    "android": "chrome_android",
    "chrome_mobile": "chrome_android",
    "ios": "safari_ios",
    "safari_mobile": "safari_ios",
    "firefox_latest": "firefox",
    "edge_latest": "edge",
    "safari_latest": "safari",
    "tor_latest": "tor",
}


def resolve_impersonate(value: str | bool | None) -> str | None:
    if value is None or value is False:
        return None
    if value is True:
        return "chrome"
    if not isinstance(value, str):
        raise ImpersonationError("impersonate must be a browser profile name, True, or None")

    profile = value.strip().lower().replace("-", "_")
    profile = _ALIASES.get(profile, profile)
    if not profile:
        return None
    if _SUPPORTED and profile not in _SUPPORTED:
        supported = ", ".join(sorted(_SUPPORTED))
        raise ImpersonationError(
            f"Unsupported browser profile {value!r}. Installed curl_cffi supports: {supported}"
        )
    return profile


def available_profiles(include_aliases: bool = False) -> tuple[str, ...]:
    profiles = set(_SUPPORTED)
    if include_aliases:
        profiles.update(_ALIASES)
    return tuple(sorted(profiles))
