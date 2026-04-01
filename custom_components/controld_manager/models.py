"""Typed models for Control D Manager."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ControlDProfileSummary:
    """Minimal future-facing model for a Control D profile."""

    profile_id: str
    name: str