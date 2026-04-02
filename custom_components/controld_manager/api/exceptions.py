"""Exception taxonomy for the Control D API layer."""

from __future__ import annotations


class ControlDApiError(Exception):
    """Base exception for Control D API failures."""


class ControlDApiAuthError(ControlDApiError):
    """Authentication to the Control D API failed."""


class ControlDApiConnectionError(ControlDApiError):
    """A network-level error occurred while contacting Control D."""


class ControlDApiResponseError(ControlDApiError):
    """The Control D API returned an unexpected response payload."""
