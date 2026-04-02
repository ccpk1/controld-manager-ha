"""Button platform for Control D Manager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .entity import ControlDManagerInstanceEntity
from .models import ControlDManagerRuntime

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[ControlDManagerRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Control D buttons for one config entry."""
    runtime = config_entry.runtime_data
    runtime.managers.entity.register_platform(
        "button",
        async_add_entities,
        lambda key: _build_button_entity(config_entry, key),
    )
    await runtime.managers.entity.async_sync_platform("button")

    @callback
    def _async_handle_coordinator_update() -> None:
        hass.async_create_task(runtime.managers.entity.async_sync_platform("button"))

    config_entry.async_on_unload(
        runtime.active_coordinator.async_add_listener(_async_handle_coordinator_update)
    )


def _build_button_entity(
    config_entry: ConfigEntry[ControlDManagerRuntime], key: str
) -> ButtonEntity:
    """Build one button entity from the entity-manager key."""
    if key == "instance::sync":
        return ControlDManagerSyncButton(config_entry)
    raise ValueError(f"Unsupported Control D button key {key!r}")


class ControlDManagerSyncButton(ControlDManagerInstanceEntity, ButtonEntity):
    """Run an on-demand account sync."""

    _attr_translation_key = "sync"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _purpose = "instance_action"

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the manual sync button."""
        super().__init__(config_entry, "sync")
        self._attr_name = "Sync now"

    async def async_press(self) -> None:
        """Run a one-shot refresh for the current account state."""
        await self.runtime.active_coordinator.async_run_manual_refresh()
        if self.runtime.sync_status.last_refresh_error is not None:
            raise HomeAssistantError(self.runtime.sync_status.last_refresh_error)
