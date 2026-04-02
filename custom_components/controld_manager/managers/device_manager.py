"""Device-manager skeleton for the Control D runtime."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from ..const import DOMAIN, MANUFACTURER, MODEL_INSTANCE, MODEL_PROFILE
from ..models import ControlDRegistry
from .base_manager import BaseManager


class DeviceManager(BaseManager):
    """Own Home Assistant device-registry lifecycle for the runtime."""

    def __init__(self) -> None:
        """Initialize the device manager."""
        super().__init__()
        self._instance_device_id: str | None = None
        self._profile_device_ids: dict[str, str] = {}

    def sync_registry(self, registry: ControlDRegistry) -> None:
        """Sync the instance and profile devices for the current registry."""
        device_registry = dr.async_get(self.runtime.active_coordinator.hass)
        managed_profile_pks = self.runtime.options.included_profile_pks(
            set(registry.profiles)
        )

        instance_entry = device_registry.async_get_or_create(
            config_entry_id=self.runtime.entry_id,
            identifiers={self.instance_identifier},
            manufacturer=MANUFACTURER,
            model=MODEL_INSTANCE,
            name="Account",
        )
        self._instance_device_id = instance_entry.id

        current_profile_device_ids: dict[str, str] = {}
        for profile in registry.profiles.values():
            if profile.profile_pk not in managed_profile_pks:
                continue
            profile_entry = device_registry.async_get_or_create(
                config_entry_id=self.runtime.entry_id,
                identifiers={self.profile_identifier(profile.profile_pk)},
                manufacturer=MANUFACTURER,
                model=MODEL_PROFILE,
                name=profile.name,
                via_device=self.instance_identifier,
            )
            current_profile_device_ids[profile.profile_pk] = profile_entry.id

        for stale_profile_pk in set(self._profile_device_ids) - set(
            current_profile_device_ids
        ):
            device_registry.async_update_device(
                self._profile_device_ids[stale_profile_pk],
                remove_config_entry_id=self.runtime.entry_id,
            )

        self._profile_device_ids = current_profile_device_ids

    @property
    def instance_identifier(self) -> tuple[str, str]:
        """Return the instance device identifier."""
        return (DOMAIN, f"instance::{self.runtime.instance_id}")

    @property
    def managed_profile_pks(self) -> set[str]:
        """Return the currently managed profile identifiers."""
        return set(self._profile_device_ids)

    def profile_identifier(self, profile_pk: str) -> tuple[str, str]:
        """Return the profile device identifier."""
        return (DOMAIN, f"instance::{self.runtime.instance_id}::profile::{profile_pk}")

    def instance_device_info(self) -> DeviceInfo:
        """Return device info for the instance system device."""
        return DeviceInfo(
            identifiers={self.instance_identifier},
            manufacturer=MANUFACTURER,
            model=MODEL_INSTANCE,
            name="Account",
        )

    def profile_device_info(self, profile_pk: str) -> DeviceInfo | None:
        """Return device info for a profile device when it is known."""
        profile = self.runtime.registry.profiles.get(profile_pk)
        if profile is None or profile_pk not in self._profile_device_ids:
            return None
        return DeviceInfo(
            identifiers={self.profile_identifier(profile_pk)},
            manufacturer=MANUFACTURER,
            model=MODEL_PROFILE,
            name=profile.name,
            via_device=self.instance_identifier,
        )

    async def async_attach_entity_to_profile(
        self, entity_id: str, profile_pk: str | None
    ) -> None:
        """Attach an entity registry entry to the current owning profile device."""
        entity_registry = er.async_get(self.runtime.active_coordinator.hass)
        if profile_pk is None:
            entity_registry.async_update_entity(entity_id, device_id=None)
            return

        device_id = self._profile_device_ids.get(profile_pk)
        if device_id is None:
            return

        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None or entity_entry.device_id == device_id:
            return

        entity_registry.async_update_entity(entity_id, device_id=device_id)

    def resolve_profile_targets_from_device_ids(self, device_ids: set[str]) -> set[str]:
        """Resolve profile targets from Control D device-registry ids."""
        if not device_ids:
            return set()

        device_registry = dr.async_get(self.runtime.active_coordinator.hass)
        targeted_profiles: set[str] = set()
        for device_id in device_ids:
            device_entry = device_registry.async_get(device_id)
            if device_entry is None:
                raise ValueError(f"Unknown device_id {device_id}")
            identifiers = set(device_entry.identifiers)
            if self.instance_identifier in identifiers:
                targeted_profiles.update(self.managed_profile_pks)
                continue

            matched_profile = next(
                (
                    profile_pk
                    for profile_pk in self.managed_profile_pks
                    if self.profile_identifier(profile_pk) in identifiers
                ),
                None,
            )
            if matched_profile is None:
                raise ValueError(
                    f"Device {device_id} does not map to a Control D profile target"
                )
            targeted_profiles.add(matched_profile)

        return targeted_profiles
