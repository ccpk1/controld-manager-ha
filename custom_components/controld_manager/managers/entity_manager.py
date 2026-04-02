"""Entity-manager skeleton for the Control D runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.helpers.entity import Entity

from ..models import ControlDRegistry
from .base_manager import BaseManager


@dataclass(slots=True)
class RegisteredPlatform:
    """Entity-manager registration for one Home Assistant platform."""

    add_entities: Callable[[list[Entity]], None]
    factory: Callable[[str], Entity]
    live_entities: dict[str, Entity] = field(default_factory=dict)


class EntityManager(BaseManager):
    """Own dynamic entity lifecycle for the runtime."""

    def __init__(self) -> None:
        """Initialize the entity manager."""
        super().__init__()
        self._registered_platforms: dict[str, RegisteredPlatform] = {}

    def sync_registry(self, registry: ControlDRegistry) -> None:
        """Store the current registry snapshot for platform reconciliation."""
        del registry

    def register_platform(
        self,
        platform: str,
        add_entities: Callable[[list[Entity]], None],
        factory: Callable[[str], Entity],
    ) -> None:
        """Register one platform for dynamic add and remove handling."""
        self._registered_platforms[platform] = RegisteredPlatform(
            add_entities=add_entities,
            factory=factory,
        )

    async def async_sync_platform(self, platform: str) -> None:
        """Synchronize a platform's live entities with the current registry."""
        registered = self._registered_platforms[platform]
        desired_keys = self._desired_keys(platform)
        live_keys = set(registered.live_entities)

        new_keys = desired_keys - live_keys
        if new_keys:
            new_entities = [registered.factory(key) for key in sorted(new_keys)]
            for key, entity in zip(sorted(new_keys), new_entities, strict=True):
                registered.live_entities[key] = entity
            registered.add_entities(new_entities)

        stale_keys = live_keys - desired_keys
        for stale_key in stale_keys:
            entity = registered.live_entities.pop(stale_key)
            # Dynamic entity creation and coordinator refreshes can overlap.
            # If Home Assistant has not attached the entity yet, there is
            # nothing to remove from the entity platform.
            if entity.hass is None:
                continue
            await entity.async_remove(force_remove=True)

        if platform == "binary_sensor":
            await self._async_reconcile_endpoint_sensor_attachments()

    def _desired_keys(self, platform: str) -> set[str]:
        """Return the desired entity keys for one platform."""
        included_profiles = self.runtime.options.included_profile_pks(
            set(self.runtime.registry.profiles)
        )
        if platform == "sensor":
            return {
                "instance::status",
                "instance::profile_count",
                "instance::endpoint_count",
            }
        if platform == "button":
            return {"instance::sync"}
        if platform == "binary_sensor":
            desired_keys: set[str] = set()
            for endpoint in self.runtime.registry.endpoints.values():
                if endpoint.owning_profile_pk is None:
                    continue
                if endpoint.owning_profile_pk not in included_profiles:
                    continue
                profile_policy = self.runtime.options.profile_policy(
                    endpoint.owning_profile_pk
                )
                if profile_policy.endpoint_sensors_enabled:
                    desired_keys.add(f"endpoint::{endpoint.device_id}::status")
            return desired_keys
        if platform == "switch":
            desired_keys = {
                f"profile::{profile_pk}::paused" for profile_pk in included_profiles
            }
            for profile_pk in included_profiles:
                desired_keys.update(
                    f"profile::{profile_pk}::filter::{filter_pk}"
                    for filter_pk in self.runtime.registry.filters_by_profile.get(
                        profile_pk, {}
                    )
                )
                desired_keys.update(
                    f"profile::{profile_pk}::service::{service_pk}"
                    for service_pk in self.runtime.registry.services_by_profile.get(
                        profile_pk, {}
                    )
                )
                desired_keys.update(
                    f"profile::{profile_pk}::rule::{rule_identity}"
                    for rule_identity in self.runtime.options.profile_policy(
                        profile_pk
                    ).exposed_rule_identities(
                        self.runtime.registry.rules_by_profile.get(profile_pk, {})
                    )
                    if rule_identity
                    in self.runtime.registry.rules_by_profile.get(profile_pk, {})
                )
            return desired_keys
        if platform == "select":
            select_keys: set[str] = set()
            for profile_pk in included_profiles:
                profile_filters = self.runtime.registry.filters_by_profile.get(
                    profile_pk, {}
                )
                select_keys.update(
                    f"profile::{profile_pk}::filter_mode::{filter_pk}"
                    for filter_pk, filter_row in profile_filters.items()
                    if filter_row.supports_modes
                )
            return select_keys
        raise ValueError(f"Unsupported Control D platform {platform!r}")

    async def _async_reconcile_endpoint_sensor_attachments(self) -> None:
        """Ensure endpoint entities remain attached to the owning profile device."""
        registered = self._registered_platforms.get("binary_sensor")
        if registered is None:
            return

        for key, entity in registered.live_entities.items():
            if not key.startswith("endpoint::") or entity.entity_id is None:
                continue
            endpoint_device_id = key.split("::", 2)[1]
            endpoint = self.runtime.registry.endpoints.get(endpoint_device_id)
            if endpoint is None:
                continue
            await self.runtime.managers.device.async_attach_entity_to_profile(
                entity.entity_id, endpoint.owning_profile_pk
            )
