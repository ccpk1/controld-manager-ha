"""Control D Manager integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

ControlDManagerConfigEntry = ConfigEntry[None]


async def async_setup_entry(
    hass: HomeAssistant, entry: ControlDManagerConfigEntry
) -> bool:
    """Set up Control D Manager from a config entry."""
    del hass
    entry.runtime_data = None
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ControlDManagerConfigEntry
) -> bool:
    """Unload a config entry."""
    del hass
    del entry
    return True