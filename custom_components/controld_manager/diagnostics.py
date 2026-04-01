"""Diagnostics support for Control D Manager."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ControlDManagerConfigEntry

TO_REDACT: set[str] = {"api_key", "token", "secret"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ControlDManagerConfigEntry
) -> dict[str, Any]:
    """Return placeholder diagnostics for a config entry."""
    del hass
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "note": "Implementation scaffold only; runtime diagnostics are not available yet.",
    }