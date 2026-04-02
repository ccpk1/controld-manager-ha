"""Diagnostics support for Control D Manager."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ControlDManagerConfigEntry
from .const import CONF_API_TOKEN

TO_REDACT: set[str] = {"api_key", "token", "secret", CONF_API_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ControlDManagerConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    del hass
    runtime = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "runtime": None
        if runtime is None
        else {
            "instance_id": runtime.instance_id,
            "profile_count": len(runtime.registry.profiles),
            "endpoint_count": (
                runtime.registry.endpoint_inventory.protected_endpoint_count
            ),
            "discovered_endpoint_count": (
                runtime.registry.endpoint_inventory.discovered_endpoint_count
            ),
            "router_client_count": (
                runtime.registry.endpoint_inventory.router_client_count
            ),
        },
    }
