"""Switch platform for Control D Manager."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .api import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from .const import (
    ATTR_GROUP,
    ATTR_PAUSED_UNTIL,
    ATTR_RULE_IDENTITY,
    DEFAULT_ENABLED_FILTERS,
    DEFAULT_PAUSE_MINUTES,
)
from .entity import ControlDManagerProfileEntity
from .models import (
    ControlDFilter,
    ControlDManagerRuntime,
    ControlDRule,
    ControlDService,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[ControlDManagerRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Control D switches for one config entry."""
    runtime = config_entry.runtime_data
    runtime.managers.entity.register_platform(
        "switch",
        async_add_entities,
        lambda key: _build_switch_entity(config_entry, key),
    )
    await runtime.managers.entity.async_sync_platform("switch")

    @callback
    def _async_handle_coordinator_update() -> None:
        hass.async_create_task(runtime.managers.entity.async_sync_platform("switch"))

    config_entry.async_on_unload(
        runtime.active_coordinator.async_add_listener(_async_handle_coordinator_update)
    )


def _build_switch_entity(
    config_entry: ConfigEntry[ControlDManagerRuntime], key: str
) -> SwitchEntity:
    """Build one switch entity from the entity-manager key."""
    if key.startswith("profile::") and key.endswith("::paused"):
        profile_pk = key.split("::", 2)[1]
        return ControlDManagerProfilePausedSwitch(config_entry, profile_pk)
    if "::filter::" in key:
        _, profile_pk, _, filter_pk = key.split("::", 3)
        return ControlDManagerProfileFilterSwitch(config_entry, profile_pk, filter_pk)
    if "::service::" in key:
        _, profile_pk, _, service_pk = key.split("::", 3)
        return ControlDManagerProfileServiceSwitch(config_entry, profile_pk, service_pk)
    if "::rule::" in key:
        _, profile_pk, _, rule_identity = key.split("::", 3)
        return ControlDManagerProfileRuleSwitch(config_entry, profile_pk, rule_identity)
    raise ValueError(f"Unsupported Control D switch key {key!r}")


class ControlDManagerProfilePausedSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for the documented profile pause state."""

    _attr_translation_key = "paused"
    _purpose = "profile_pause"

    def __init__(
        self, config_entry: ConfigEntry[ControlDManagerRuntime], profile_pk: str
    ) -> None:
        """Initialize the profile paused switch."""
        super().__init__(config_entry, profile_pk, "paused")
        self._attr_name = "Disable"

    @property
    def is_on(self) -> bool:
        """Return whether the profile is currently paused."""
        profile = self.profile
        if profile is None or profile.paused_until is None:
            return False
        return bool(profile.paused_until > dt_util.utcnow().astimezone(UTC))

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the current paused-until timestamp when available."""
        profile = self.profile
        attributes = super().extra_state_attributes or {}
        if profile is not None and profile.paused_until is not None:
            attributes[ATTR_PAUSED_UNTIL] = profile.paused_until.isoformat()
        return attributes

    def turn_on(self, **kwargs: object) -> None:
        """Switch turn_on is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    def turn_off(self, **kwargs: object) -> None:
        """Switch turn_off is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: object) -> None:
        """Pause the profile using the default service-compatible duration."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_pause_profiles(
                {self._profile_pk}, DEFAULT_PAUSE_MINUTES
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to pause the Control D profile") from err

    async def async_turn_off(self, **kwargs: object) -> None:
        """Resume the profile immediately."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_resume_profiles(
                {self._profile_pk}
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to resume the Control D profile") from err


class ControlDManagerProfileFilterSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for one auto-created profile filter."""

    _purpose = "profile_filter"

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        filter_pk: str,
    ) -> None:
        """Initialize one profile filter switch."""
        self._filter_pk = filter_pk
        super().__init__(config_entry, profile_pk, f"filter::{filter_pk}")
        filter_row = self.filter_row
        self._attr_name = (
            f"Filters / {filter_row.name}"
            if filter_row is not None
            else f"Filters / {filter_pk}"
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
        """Return whether the filter still exists in the registry."""
        return super().available and self.filter_row is not None

    @property
    def is_on(self) -> bool:
        """Return whether the filter is enabled."""
        filter_row = self.filter_row
        return bool(filter_row is not None and filter_row.enabled)

    def turn_on(self, **kwargs: object) -> None:
        """Switch turn_on is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    def turn_off(self, **kwargs: object) -> None:
        """Switch turn_off is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the filter."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_filter_enabled(
                self._profile_pk, self._filter_pk, True
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to enable the Control D filter") from err

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the filter."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_filter_enabled(
                self._profile_pk, self._filter_pk, False
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to disable the Control D filter") from err


class ControlDManagerProfileServiceSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for one dynamically exposed service."""

    _purpose = "profile_service"

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        service_pk: str,
    ) -> None:
        """Initialize one service switch."""
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
    def is_on(self) -> bool:
        """Return whether the service rule is enabled."""
        service_row = self.service_row
        return bool(service_row is not None and service_row.enabled)

    def turn_on(self, **kwargs: object) -> None:
        """Switch turn_on is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    def turn_off(self, **kwargs: object) -> None:
        """Switch turn_off is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the service rule."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_service_enabled(
                self._profile_pk, self._service_pk, True
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to enable the Control D service") from err

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the service rule."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_service_enabled(
                self._profile_pk, self._service_pk, False
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to disable the Control D service") from err


class ControlDManagerProfileRuleSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for one explicitly selected rule."""

    _purpose = "profile_rule"

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        rule_identity: str,
    ) -> None:
        """Initialize one selected rule switch."""
        self._rule_identity = rule_identity
        super().__init__(config_entry, profile_pk, f"rule::{rule_identity}")
        rule_row = self.rule_row
        if rule_row is None:
            self._attr_name = f"Rules / {rule_identity}"
        elif rule_row.group_name:
            self._attr_name = f"Rules / {rule_row.group_name} / {rule_row.rule_pk}"
        else:
            self._attr_name = f"Rules / Domain / {rule_row.rule_pk}"

    @property
    def rule_row(self) -> ControlDRule | None:
        """Return the current normalized rule row."""
        return self.runtime.registry.rules_by_profile.get(self._profile_pk, {}).get(
            self._rule_identity
        )

    @property
    def available(self) -> bool:
        """Return whether the rule still exists in the registry."""
        return super().available and self.rule_row is not None

    @property
    def is_on(self) -> bool:
        """Return whether the rule is enabled."""
        rule_row = self.rule_row
        return bool(rule_row is not None and rule_row.enabled)

    def turn_on(self, **kwargs: object) -> None:
        """Switch turn_on is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    def turn_off(self, **kwargs: object) -> None:
        """Switch turn_off is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose the stable rule identity and optional group name."""
        attributes = super().extra_state_attributes or {}
        attributes[ATTR_RULE_IDENTITY] = self._rule_identity
        rule_row = self.rule_row
        if rule_row is not None and rule_row.group_name is not None:
            attributes[ATTR_GROUP] = rule_row.group_name
        return attributes

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the selected rule."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_rule_enabled(
                self._profile_pk, self._rule_identity, True
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to enable the Control D rule") from err

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the selected rule."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_rule_enabled(
                self._profile_pk, self._rule_identity, False
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError("Unable to disable the Control D rule") from err
