"""Select platform for Control D Manager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .api import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from .entity import ControlDManagerProfileEntity
from .models import ControlDFilter, ControlDManagerRuntime

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[ControlDManagerRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Control D selects for one config entry."""
    runtime = config_entry.runtime_data
    runtime.managers.entity.register_platform(
        "select",
        async_add_entities,
        lambda key: _build_select_entity(config_entry, key),
    )
    await runtime.managers.entity.async_sync_platform("select")

    @callback
    def _async_handle_coordinator_update() -> None:
        hass.async_create_task(runtime.managers.entity.async_sync_platform("select"))

    config_entry.async_on_unload(
        runtime.active_coordinator.async_add_listener(_async_handle_coordinator_update)
    )


def _build_select_entity(
    config_entry: ConfigEntry[ControlDManagerRuntime], key: str
) -> SelectEntity:
    """Build one select entity from the entity-manager key."""
    if "::filter_mode::" in key:
        _, profile_pk, _, filter_pk = key.split("::", 3)
        return ControlDManagerProfileFilterModeSelect(
            config_entry, profile_pk, filter_pk
        )
    raise ValueError(f"Unsupported Control D select key {key!r}")


class ControlDManagerProfileFilterModeSelect(
    ControlDManagerProfileEntity, SelectEntity
):
    """Select surface for modal profile filters."""

    _purpose = "profile_filter_mode"

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        filter_pk: str,
    ) -> None:
        """Initialize one filter-mode select."""
        self._filter_pk = filter_pk
        super().__init__(config_entry, profile_pk, f"filter_mode::{filter_pk}")
        filter_row = self.filter_row
        self._attr_name = (
            f"Filters / {filter_row.name} Mode"
            if filter_row is not None
            else f"Filters / {filter_pk} Mode"
        )

    @property
    def filter_row(self) -> ControlDFilter | None:
        """Return the current normalized filter row."""
        return self.runtime.registry.filters_by_profile.get(self._profile_pk, {}).get(
            self._filter_pk
        )

    @property
    def available(self) -> bool:
        """Return whether the filter still exists and supports modes."""
        filter_row = self.filter_row
        return bool(
            super().available and filter_row is not None and filter_row.supports_modes
        )

    @property
    def options(self) -> list[str]:
        """Return the available mode labels."""
        filter_row = self.filter_row
        if filter_row is None:
            return []
        return [level.title for level in filter_row.levels]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected mode label."""
        filter_row = self.filter_row
        if filter_row is None:
            return None
        for level in filter_row.levels:
            if level.slug == filter_row.selected_level_slug:
                return str(level.title)
        return None

    def select_option(self, option: str) -> None:
        """Select option is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        """Select a new mode for the filter."""
        filter_row = self.filter_row
        if filter_row is None:
            raise HomeAssistantError("Unable to find the selected Control D filter")
        selected_level = next(
            (level for level in filter_row.levels if level.title == option),
            None,
        )
        if selected_level is None:
            raise HomeAssistantError("Unsupported Control D filter mode")
        try:
            await self.runtime.managers.profile.async_set_filter_mode(
                self._profile_pk, self._filter_pk, selected_level.slug
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError(
                "Unable to update the Control D filter mode"
            ) from err
