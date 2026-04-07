"""Switch platform for Control D Manager."""

from __future__ import annotations

from datetime import UTC, datetime
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
    ATTR_ACTION,
    ATTR_COMMENT,
    ATTR_EXPIRED,
    ATTR_EXPIRES_AT,
    ATTR_GROUP,
    ATTR_PAUSED_UNTIL,
    ATTR_RULE_IDENTITY,
    DEFAULT_DISABLE_MINUTES,
    DEFAULT_ENABLED_FILTERS,
    DOMAIN,
    PURPOSE_PROFILE_FILTER,
    PURPOSE_PROFILE_OPTION,
    PURPOSE_PROFILE_PAUSE,
    PURPOSE_PROFILE_RULE,
    TRANS_KEY_DISABLE_FILTER_FAILED,
    TRANS_KEY_DISABLE_OPTION_FAILED,
    TRANS_KEY_DISABLE_PROFILE_FAILED,
    TRANS_KEY_DISABLE_RULE_FAILED,
    TRANS_KEY_ENABLE_FILTER_FAILED,
    TRANS_KEY_ENABLE_OPTION_FAILED,
    TRANS_KEY_ENABLE_PROFILE_FAILED,
    TRANS_KEY_ENABLE_RULE_FAILED,
)
from .entity import ControlDManagerProfileEntity
from .models import (
    ControlDFilter,
    ControlDManagerRuntime,
    ControlDProfileOption,
    ControlDRule,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

PARALLEL_UPDATES = 0


def _ha_error(translation_key: str) -> HomeAssistantError:
    """Build one translated Home Assistant error."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=translation_key,
    )


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
    if "::rule::" in key:
        _, profile_pk, _, rule_identity = key.split("::", 3)
        return ControlDManagerProfileRuleSwitch(config_entry, profile_pk, rule_identity)
    if "::option::" in key:
        _, profile_pk, _, option_pk = key.split("::", 3)
        return ControlDManagerProfileOptionSwitch(config_entry, profile_pk, option_pk)
    raise ValueError(f"Unsupported Control D switch key {key!r}")


class ControlDManagerProfilePausedSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for the documented profile disable state."""

    _attr_translation_key = "paused"
    _purpose = PURPOSE_PROFILE_PAUSE

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
        """Disable the profile using the default service-compatible duration."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_disable_profiles(
                {self._profile_pk}, DEFAULT_DISABLE_MINUTES
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_DISABLE_PROFILE_FAILED) from err

    async def async_turn_off(self, **kwargs: object) -> None:
        """Enable the profile immediately."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_enable_profiles(
                {self._profile_pk}
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_ENABLE_PROFILE_FAILED) from err


class ControlDManagerProfileFilterSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for one auto-created profile filter."""

    _attr_translation_key = "profile_filter"
    _purpose = PURPOSE_PROFILE_FILTER

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
            filter_row is not None
            and not filter_row.external
            and filter_pk in DEFAULT_ENABLED_FILTERS
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
            raise _ha_error(TRANS_KEY_ENABLE_FILTER_FAILED) from err

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
            raise _ha_error(TRANS_KEY_DISABLE_FILTER_FAILED) from err


class ControlDManagerProfileRuleSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for one explicitly selected rule."""

    _attr_translation_key = "profile_rule"
    _purpose = PURPOSE_PROFILE_RULE

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
        return bool(
            rule_row is not None
            and rule_row.enabled
            and not self._rule_is_expired(rule_row)
        )

    @staticmethod
    def _rule_is_expired(rule_row: ControlDRule) -> bool:
        """Return whether the rule expiration is in the past."""
        if rule_row.ttl is None:
            return False
        return bool(datetime.fromtimestamp(rule_row.ttl, UTC) <= dt_util.utcnow())

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
        if rule_row is not None:
            if rule_row.group_name is not None:
                attributes[ATTR_GROUP] = rule_row.group_name
            attributes[ATTR_COMMENT] = rule_row.comment
            attributes[ATTR_ACTION] = rule_row.action_key
            if rule_row.ttl is not None:
                expires_at = datetime.fromtimestamp(rule_row.ttl, UTC)
                attributes[ATTR_EXPIRES_AT] = expires_at.isoformat()
                attributes[ATTR_EXPIRED] = self._rule_is_expired(rule_row)
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
            raise _ha_error(TRANS_KEY_ENABLE_RULE_FAILED) from err

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
            raise _ha_error(TRANS_KEY_DISABLE_RULE_FAILED) from err


class ControlDManagerProfileOptionSwitch(ControlDManagerProfileEntity, SwitchEntity):
    """Switch surface for one toggle-style profile option."""

    _attr_translation_key = "profile_option"
    _purpose = PURPOSE_PROFILE_OPTION

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        option_pk: str,
    ) -> None:
        """Initialize one profile option switch."""
        self._option_pk = option_pk
        super().__init__(config_entry, profile_pk, f"option::{option_pk}")
        option_row = self.option_row
        self._attr_name = (
            f"Options / {option_row.title}"
            if option_row is not None
            else f"Options / {option_pk}"
        )
        self._attr_entity_registry_enabled_default = option_pk in {
            "safesearch",
            "safeyoutube",
        }

    @property
    def option_row(self) -> ControlDProfileOption | None:
        """Return the current normalized option row."""
        return self.runtime.registry.options_by_profile.get(self._profile_pk, {}).get(
            self._option_pk
        )

    @property
    def available(self) -> bool:
        """Return whether the option still exists and supports toggle behavior."""
        option_row = self.option_row
        return bool(
            super().available
            and option_row is not None
            and option_row.entity_kind == "toggle"
        )

    @property
    def is_on(self) -> bool:
        """Return whether the option is enabled."""
        option_row = self.option_row
        return bool(option_row is not None and option_row.is_enabled)

    def turn_on(self, **kwargs: object) -> None:
        """Switch turn_on is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    def turn_off(self, **kwargs: object) -> None:
        """Switch turn_off is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the profile option."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_profile_option_toggle(
                self._profile_pk, self._option_pk, True
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_ENABLE_OPTION_FAILED) from err

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the profile option."""
        del kwargs
        try:
            await self.runtime.managers.profile.async_set_profile_option_toggle(
                self._profile_pk, self._option_pk, False
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_DISABLE_OPTION_FAILED) from err
