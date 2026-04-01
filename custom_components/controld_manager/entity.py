"""Base entity placeholders for Control D Manager."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN


class ControlDManagerEntity(Entity):
    """Base entity placeholder for future Control D surfaces."""

    _attr_has_entity_name = True

    def __init__(self, profile_id: str) -> None:
        """Initialize the base entity."""
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, profile_id)},
        )