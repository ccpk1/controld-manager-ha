"""Binary sensor platform for Control D Manager."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ACTIVITY_THRESHOLD_MINUTES,
    ATTR_ATTACHED_PROFILES,
    ATTR_LAST_ACTIVE,
    ATTR_PARENT_DEVICE_ID,
    PURPOSE_ENDPOINT_STATUS,
)
from .entity import ControlDManagerEndpointEntity
from .models import ControlDManagerRuntime

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[ControlDManagerRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Control D binary sensors for one config entry."""
    runtime = config_entry.runtime_data
    runtime.managers.entity.register_platform(
        "binary_sensor",
        async_add_entities,
        lambda key: _build_binary_sensor_entity(config_entry, key),
    )
    await runtime.managers.entity.async_sync_platform("binary_sensor")

    @callback
    def _async_handle_coordinator_update() -> None:
        hass.async_create_task(
            runtime.managers.entity.async_sync_platform("binary_sensor")
        )

    config_entry.async_on_unload(
        runtime.active_coordinator.async_add_listener(_async_handle_coordinator_update)
    )


def _build_binary_sensor_entity(
    config_entry: ConfigEntry[ControlDManagerRuntime], key: str
) -> BinarySensorEntity:
    """Build one binary sensor entity from the entity-manager key."""
    if key.startswith("endpoint::") and key.endswith("::status"):
        endpoint_device_id = key.split("::", 2)[1]
        return ControlDManagerEndpointStatusBinarySensor(
            config_entry, endpoint_device_id
        )
    raise ValueError(f"Unsupported Control D binary sensor key {key!r}")


class ControlDManagerEndpointStatusBinarySensor(
    ControlDManagerEndpointEntity, BinarySensorEntity
):
    """Compact endpoint status surface derived from last activity."""

    _attr_translation_key = "endpoint_status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _purpose = PURPOSE_ENDPOINT_STATUS

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        endpoint_device_id: str,
    ) -> None:
        """Initialize the endpoint status binary sensor."""
        super().__init__(config_entry, endpoint_device_id, "status")
        endpoint = self.endpoint
        endpoint_name = (
            endpoint.name
            if endpoint is not None and endpoint.name
            else endpoint_device_id
        )
        self._attr_name = f"{endpoint_name} Status"

    @property
    def _activity_threshold(self) -> timedelta:
        """Return the current endpoint-status activity threshold."""
        endpoint = self.endpoint
        if endpoint is None or endpoint.owning_profile_pk is None:
            return timedelta(minutes=15)
        minutes = self.runtime.options.profile_policy(
            endpoint.owning_profile_pk
        ).endpoint_inactivity_threshold_minutes
        return timedelta(minutes=minutes)

    @property
    def is_on(self) -> bool:
        """Return whether the endpoint is still considered active."""
        endpoint = self.endpoint
        if endpoint is None or endpoint.last_active is None:
            return False
        return endpoint.last_active >= dt_util.utcnow() - self._activity_threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return endpoint metadata on the compact status surface."""
        endpoint = self.endpoint
        if endpoint is None:
            return super().extra_state_attributes

        attributes: dict[str, Any] = super().extra_state_attributes or {}
        attributes[ATTR_ACTIVITY_THRESHOLD_MINUTES] = int(
            self._activity_threshold.total_seconds() // 60
        )
        attributes[ATTR_LAST_ACTIVE] = (
            endpoint.last_active.isoformat()
            if endpoint.last_active is not None
            else None
        )
        attributes[ATTR_ATTACHED_PROFILES] = [
            attached_profile.name or attached_profile.profile_pk
            for attached_profile in endpoint.attached_profiles
        ]
        attributes[ATTR_PARENT_DEVICE_ID] = endpoint.parent_device_id
        return attributes
