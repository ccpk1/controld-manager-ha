"""Sensor platform for Control D Manager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback

from .const import (
    ATTR_ACCOUNT_STATUS,
    ATTR_CONSECUTIVE_FAILED_REFRESHES,
    ATTR_DISCOVERED_ENDPOINT_COUNT,
    ATTR_LAST_REFRESH_ATTEMPT,
    ATTR_LAST_REFRESH_ERROR,
    ATTR_LAST_REFRESH_TRIGGER,
    ATTR_LAST_SUCCESSFUL_REFRESH,
    ATTR_REFRESH_IN_PROGRESS,
    ATTR_ROUTER_CLIENT_COUNT,
    ATTR_STATS_ENDPOINT,
)
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
    """Set up Control D sensors for one config entry."""
    runtime = config_entry.runtime_data
    runtime.managers.entity.register_platform(
        "sensor",
        async_add_entities,
        lambda key: _build_sensor_entity(config_entry, key),
    )
    await runtime.managers.entity.async_sync_platform("sensor")

    @callback
    def _async_handle_coordinator_update() -> None:
        hass.async_create_task(runtime.managers.entity.async_sync_platform("sensor"))

    config_entry.async_on_unload(
        runtime.active_coordinator.async_add_listener(_async_handle_coordinator_update)
    )


def _build_sensor_entity(
    config_entry: ConfigEntry[ControlDManagerRuntime], key: str
) -> SensorEntity:
    """Build one sensor entity from the entity-manager key."""
    if key == "instance::profile_count":
        return ControlDManagerProfileCountSensor(config_entry)
    if key == "instance::endpoint_count":
        return ControlDManagerEndpointCountSensor(config_entry)
    if key == "instance::status":
        return ControlDManagerStatusSensor(config_entry)
    raise ValueError(f"Unsupported Control D sensor key {key!r}")


class ControlDManagerStatusSensor(ControlDManagerInstanceEntity, SensorEntity):
    """Expose the current account and polling status."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _purpose = "instance_status"

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the account-status sensor."""
        super().__init__(config_entry, "status")
        self._attr_name = "Status"
        self._attr_options = ["healthy", "degraded", "problem"]

    @property
    def available(self) -> bool:
        """Keep the status sensor visible even when the last poll failed."""
        return True

    @property
    def native_value(self) -> str:
        """Return the current health of the Control D integration runtime."""
        sync_status = self.runtime.sync_status
        if sync_status.last_refresh_error is None:
            return "healthy"
        if (
            sync_status.consecutive_failed_refreshes == 1
            and sync_status.last_successful_refresh is not None
        ):
            return "degraded"
        return "problem"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return concise account and refresh metadata."""
        attributes = super().extra_state_attributes or {}
        user = self.runtime.registry.user
        sync_status = self.runtime.sync_status
        attributes.update(
            {
                ATTR_LAST_REFRESH_ATTEMPT: sync_status.last_refresh_attempt,
                ATTR_LAST_SUCCESSFUL_REFRESH: sync_status.last_successful_refresh,
                ATTR_REFRESH_IN_PROGRESS: sync_status.refresh_in_progress,
                ATTR_LAST_REFRESH_TRIGGER: sync_status.last_refresh_trigger,
                ATTR_CONSECUTIVE_FAILED_REFRESHES: (
                    sync_status.consecutive_failed_refreshes
                ),
            }
        )
        if user is not None and user.stats_endpoint is not None:
            attributes[ATTR_STATS_ENDPOINT] = user.stats_endpoint
        if user is not None and user.status is not None:
            attributes[ATTR_ACCOUNT_STATUS] = user.status
        if sync_status.last_refresh_error is not None:
            attributes[ATTR_LAST_REFRESH_ERROR] = sync_status.last_refresh_error
        return attributes


class ControlDManagerProfileCountSensor(ControlDManagerInstanceEntity, SensorEntity):
    """Expose the current number of discovered profiles."""

    _attr_translation_key = "profile_count"
    _purpose = "instance_summary"

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the profile-count sensor."""
        super().__init__(config_entry, "profile_count")
        self._attr_name = "Profile count"

    @property
    def native_value(self) -> int:
        """Return the current number of discovered profiles."""
        return len(self.runtime.registry.profiles)


class ControlDManagerEndpointCountSensor(ControlDManagerInstanceEntity, SensorEntity):
    """Expose the current number of discovered endpoints."""

    _attr_translation_key = "endpoint_count"
    _purpose = "instance_summary"

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the endpoint-count sensor."""
        super().__init__(config_entry, "endpoint_count")
        self._attr_name = "Endpoint count"

    @property
    def native_value(self) -> int:
        """Return the current number of discovered endpoints."""
        return self.runtime.registry.endpoint_inventory.protected_endpoint_count

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return the explicit and nested endpoint counts."""
        attributes = super().extra_state_attributes or {}
        attributes.update(
            {
                ATTR_DISCOVERED_ENDPOINT_COUNT: (
                    self.runtime.registry.endpoint_inventory.discovered_endpoint_count
                ),
                ATTR_ROUTER_CLIENT_COUNT: (
                    self.runtime.registry.endpoint_inventory.router_client_count
                ),
            }
        )
        return attributes
