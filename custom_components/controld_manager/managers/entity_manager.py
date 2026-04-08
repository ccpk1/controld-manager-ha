"""Entity-manager skeleton for the Control D runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity

from ..const import (
    ADVANCED_PROFILE_OPTION_SELECTS,
    ADVANCED_PROFILE_OPTION_TOGGLES,
    CORE_PROFILE_OPTION_SELECTS,
    CORE_PROFILE_OPTION_TOGGLES,
    DOMAIN,
)
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
        desired_unique_ids = self._desired_unique_ids(platform, desired_keys)
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

        self._async_remove_stale_registry_entries(platform, desired_unique_ids)

        if platform == "binary_sensor":
            await self._async_reconcile_endpoint_sensor_attachments()

    def _desired_unique_ids(self, platform: str, desired_keys: set[str]) -> set[str]:
        """Return the stable unique IDs that should exist for one platform."""
        registered = self._registered_platforms[platform]
        desired_unique_ids: set[str] = set()

        for key in desired_keys:
            entity = registered.live_entities.get(key)
            if entity is None:
                entity = registered.factory(key)
            if entity.unique_id is None:
                raise ValueError(
                    f"Control D {platform} entity {key!r} did not expose a unique ID"
                )
            desired_unique_ids.add(entity.unique_id)

        return desired_unique_ids

    def _async_remove_stale_registry_entries(
        self, platform: str, desired_unique_ids: set[str]
    ) -> None:
        """Remove stale registry-only entities for one platform."""
        entity_registry = er.async_get(self.runtime.active_coordinator.hass)

        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, self.runtime.entry_id
        ):
            if entity_entry.platform != DOMAIN or entity_entry.domain != platform:
                continue
            if not entity_entry.unique_id.startswith(f"{self.runtime.instance_id}::"):
                continue
            if entity_entry.unique_id in desired_unique_ids:
                continue
            entity_registry.async_remove(entity_entry.entity_id)

    def _desired_keys(self, platform: str) -> set[str]:
        """Return the desired entity keys for one platform."""
        included_profiles = self.runtime.options.included_profile_pks(
            set(self.runtime.registry.profiles)
        )
        if platform == "sensor":
            sensor_keys = {
                "instance::status",
                "instance::profile_count",
                "instance::endpoint_count",
                "instance::total_queries",
                "instance::blocked_queries",
                "instance::bypassed_queries",
                "instance::redirected_queries",
            }
            for profile_pk in included_profiles:
                sensor_keys.update(
                    {
                        f"profile::{profile_pk}::total_queries",
                        f"profile::{profile_pk}::blocked_queries",
                        f"profile::{profile_pk}::bypassed_queries",
                        f"profile::{profile_pk}::redirected_queries",
                    }
                )
            return sensor_keys
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
                    for filter_pk in self._exposed_filter_pks(profile_pk)
                )
                desired_keys.update(
                    f"profile::{profile_pk}::option::{option_pk}"
                    for option_pk in CORE_PROFILE_OPTION_TOGGLES
                    if option_pk
                    in self.runtime.registry.options_by_profile.get(profile_pk, {})
                )
                if self.runtime.options.profile_policy(
                    profile_pk
                ).advanced_profile_options:
                    desired_keys.update(
                        f"profile::{profile_pk}::option::{option_pk}"
                        for option_pk in ADVANCED_PROFILE_OPTION_TOGGLES
                        if option_pk
                        in self.runtime.registry.options_by_profile.get(profile_pk, {})
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
                profile_policy = self.runtime.options.profile_policy(profile_pk)
                if profile_pk in self.runtime.registry.default_rules_by_profile:
                    select_keys.add(f"profile::{profile_pk}::default_rule")
                select_keys.update(
                    f"profile::{profile_pk}::rule_group::{group_pk}"
                    for group_pk in self.runtime.options.profile_policy(
                        profile_pk
                    ).exposed_rule_group_pks(
                        self.runtime.registry.rule_groups_by_profile.get(profile_pk, {})
                    )
                )
                select_keys.update(
                    f"profile::{profile_pk}::filter_mode::{filter_pk}"
                    for filter_pk in self._exposed_filter_pks(
                        profile_pk,
                        require_modes=True,
                    )
                )
                select_keys.update(
                    f"profile::{profile_pk}::option::{option_pk}"
                    for option_pk in CORE_PROFILE_OPTION_SELECTS
                    if option_pk
                    in self.runtime.registry.options_by_profile.get(profile_pk, {})
                )
                if self.runtime.options.profile_policy(
                    profile_pk
                ).advanced_profile_options:
                    select_keys.update(
                        f"profile::{profile_pk}::option::{option_pk}"
                        for option_pk in ADVANCED_PROFILE_OPTION_SELECTS
                        if option_pk
                        in self.runtime.registry.options_by_profile.get(profile_pk, {})
                    )
                select_keys.update(
                    f"profile::{profile_pk}::service::{service_pk}"
                    for service_pk in self.runtime.registry.services_by_profile.get(
                        profile_pk, {}
                    )
                )
            return select_keys
        raise ValueError(f"Unsupported Control D platform {platform!r}")

    def _exposed_filter_pks(
        self,
        profile_pk: str,
        *,
        require_modes: bool = False,
    ) -> set[str]:
        """Return filter IDs that should be exposed for one profile policy."""
        profile_policy = self.runtime.options.profile_policy(profile_pk)
        profile_filters = self.runtime.registry.filters_by_profile.get(profile_pk, {})
        return {
            filter_pk
            for filter_pk, filter_row in profile_filters.items()
            if filter_pk != "ai_malware"
            if not require_modes or filter_row.supports_modes
            if not filter_row.external or profile_policy.expose_external_filters
        }

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
