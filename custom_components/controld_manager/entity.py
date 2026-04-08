"""Shared entity base classes for Control D Manager."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_PURPOSE
from .coordinator import ControlDManagerDataUpdateCoordinator
from .models import (
    ControlDEndpointSummary,
    ControlDManagerRuntime,
    ControlDProfileSummary,
)


class ControlDManagerEntity(CoordinatorEntity[ControlDManagerDataUpdateCoordinator]):
    """Shared coordinator-backed entity base for Control D Manager."""

    _attr_has_entity_name = True
    _purpose: str | None = None

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        object_scope: str,
        object_id: str,
        entity_key: str,
    ) -> None:
        """Initialize the shared coordinator-backed entity."""
        self._config_entry = config_entry
        self._runtime = config_entry.runtime_data
        self._attr_unique_id = (
            f"{self._runtime.instance_id}::{object_scope}::{object_id}::{entity_key}"
        )
        super().__init__(self._runtime.active_coordinator)

    @property
    def runtime(self) -> ControlDManagerRuntime:
        """Return the current entry-scoped runtime."""
        return self._runtime

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return shared purpose metadata when available."""
        if self._purpose is None:
            return None
        return {ATTR_PURPOSE: self._purpose}


class ControlDManagerInstanceEntity(ControlDManagerEntity):
    """Entity base attached to the instance system device."""

    def __init__(
        self, config_entry: ConfigEntry[ControlDManagerRuntime], entity_key: str
    ) -> None:
        """Initialize an instance-scoped entity."""
        super().__init__(config_entry, "instance", "system", entity_key)

    @property
    def device_info(self) -> DeviceInfo:
        """Return instance-device info for the entity."""
        return self.runtime.managers.device.instance_device_info()


class ControlDManagerProfileEntity(ControlDManagerEntity):
    """Entity base attached to one profile device."""

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        entity_key: str,
    ) -> None:
        """Initialize a profile-scoped entity."""
        self._profile_pk = profile_pk
        super().__init__(config_entry, "profile", profile_pk, entity_key)

    @property
    def profile(self) -> ControlDProfileSummary | None:
        """Return the current normalized profile model."""
        return self.runtime.registry.profiles.get(self._profile_pk)

    @property
    def available(self) -> bool:
        """Return whether the entity remains present in the registry."""
        return super().available and self.profile is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return profile-device info for the entity."""
        return self.runtime.managers.device.profile_device_info(self._profile_pk)


class ControlDManagerEndpointEntity(ControlDManagerEntity):
    """Entity base attached to the owning profile device for an endpoint."""

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        endpoint_device_id: str,
        entity_key: str,
    ) -> None:
        """Initialize an endpoint-scoped entity."""
        self._endpoint_device_id = endpoint_device_id
        self._attr_has_entity_name = False
        super().__init__(config_entry, "endpoint", endpoint_device_id, entity_key)

    @property
    def endpoint(self) -> ControlDEndpointSummary | None:
        """Return the current normalized endpoint model."""
        return self.runtime.registry.endpoints.get(self._endpoint_device_id)

    @property
    def available(self) -> bool:
        """Return whether the entity remains present in the registry."""
        return super().available and self.endpoint is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the current owning profile device for the endpoint."""
        endpoint = self.endpoint
        if endpoint is None or endpoint.owning_profile_pk is None:
            return None
        return self.runtime.managers.device.profile_device_info(
            endpoint.owning_profile_pk
        )
