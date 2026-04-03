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
from .const import DEFAULT_ENABLED_FILTERS
from .entity import ControlDManagerProfileEntity
from .models import (
    ControlDFilter,
    ControlDManagerRuntime,
    ControlDService,
    service_mode_options,
)

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
    if "::service::" in key:
        _, profile_pk, _, service_pk = key.split("::", 3)
        return ControlDManagerProfileServiceModeSelect(
            config_entry, profile_pk, service_pk
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
        self._attr_entity_registry_enabled_default = (
            filter_pk in DEFAULT_ENABLED_FILTERS
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
        return filter_row.effective_level_title

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


class ControlDManagerProfileServiceModeSelect(
    ControlDManagerProfileEntity, SelectEntity
):
    """Select surface for one dynamically exposed service."""

    _purpose = "profile_service"

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        service_pk: str,
    ) -> None:
        """Initialize one service-mode select."""
        self._service_pk = service_pk
        super().__init__(config_entry, profile_pk, f"service::{service_pk}")
        service_row = self.service_row
        self._attr_name = (
            f"Services / {service_row.category_name} / {service_row.name}"
            if service_row is not None
            else f"Services / {service_pk}"
        )
        self._attr_entity_registry_enabled_default = (
            self.runtime.options.profile_policy(profile_pk).auto_enable_service_switches
        )

    @property
    def service_row(self) -> ControlDService | None:
        """Return the current normalized service row."""
        return self.runtime.registry.services_by_profile.get(self._profile_pk, {}).get(
            self._service_pk
        )

    @property
    def available(self) -> bool:
        """Return whether the service still exists in the registry."""
        return super().available and self.service_row is not None

    @property
    def options(self) -> list[str]:
        """Return the supported service-mode options."""
        return list(service_mode_options())

    @property
    def current_option(self) -> str | None:
        """Return the current service mode."""
        service_row = self.service_row
        if service_row is None:
            return None
        return service_row.current_mode

    def select_option(self, option: str) -> None:
        """Select option is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        """Set a new mode for the service."""
        service_row = self.service_row
        if service_row is None:
            raise HomeAssistantError("Unable to find the selected Control D service")
        if option not in service_mode_options():
            raise HomeAssistantError("Unsupported Control D service mode")
        try:
            await self.runtime.managers.profile.async_set_service_mode(
                self._profile_pk, self._service_pk, option
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to update the Control D service") from err
