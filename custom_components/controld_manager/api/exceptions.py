"""Exception taxonomy for the Control D API layer."""

from __future__ import annotations

# Analytics maintenance responses carry this error code alongside HTTP 503.
ANALYTICS_MAINTENANCE_CODE = "50303"


class ControlDApiError(Exception):
    """Base exception for Control D API failures."""

    @property
    def retryable(self) -> bool:
        """Return whether the caller may usefully retry the same request."""
        return False


class ControlDApiAuthError(ControlDApiError):
    """Authentication to the Control D API failed."""


class ControlDApiConnectionError(ControlDApiError):
    """A network-level error occurred while contacting Control D."""

    @property
    def retryable(self) -> bool:
        """A transport failure may succeed when retried."""
        return True


class ControlDApiResponseError(ControlDApiError):
    """The Control D API returned an unexpected response payload."""


class ControlDApiMaintenanceError(ControlDApiResponseError):
    """Analytics is in maintenance mode and cannot serve the request."""

    @property
    def retryable(self) -> bool:
        """Maintenance is transient, so a later retry may succeed."""
        return True


class ControlDApiRateLimitError(ControlDApiResponseError):
    """Control D rate limited the request."""

    @property
    def retryable(self) -> bool:
        """A rate-limited request may succeed after a delay."""
        return True
