"""Coordinator placeholders for Control D Manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ControlDManagerRuntime:
    """Placeholder runtime model for future coordinator-backed data."""

    account: dict[str, Any] | None = None
    analytics: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None