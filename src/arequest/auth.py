"""Authentication handlers for arequest."""

import base64
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass  # No dependencies needed


class AuthBase:
    """Base class for authentication handlers."""

    def apply(self, request: Any) -> None:
        """Apply authentication to request.

        Args:
            request: Request object with headers attribute
        """
        raise NotImplementedError


class BasicAuth(AuthBase):
    """Basic HTTP authentication."""

    def __init__(self, username: str, password: str) -> None:
        """Initialize BasicAuth.

        Args:
            username: Username
            password: Password
        """
        self.username = username
        self.password = password

    def apply(self, request: Any) -> None:
        """Apply basic authentication to request.

        Args:
            request: Request object with headers attribute
        """
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"


class BearerAuth(AuthBase):
    """Bearer token authentication."""

    def __init__(self, token: str) -> None:
        """Initialize BearerAuth.

        Args:
            token: Bearer token
        """
        self.token = token

    def apply(self, request: Any) -> None:
        """Apply bearer authentication to request.

        Args:
            request: Request object with headers attribute
        """
        request.headers["Authorization"] = f"Bearer {self.token}"

