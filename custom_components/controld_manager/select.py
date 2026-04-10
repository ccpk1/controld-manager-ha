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
from .const import (
    ATTR_REDIRECT_TARGET,
    ATTR_REDIRECT_TARGET_TYPE,
    ATTR_SUGGESTED_REDIRECT_TARGET,
    DEFAULT_ENABLED_FILTERS,
    DOMAIN,
    PURPOSE_PROFILE_DEFAULT_RULE,
    PURPOSE_PROFILE_FILTER_MODE,
    PURPOSE_PROFILE_OPTION,
    PURPOSE_PROFILE_RULE_GROUP,
    PURPOSE_PROFILE_SERVICE,
    TRANS_KEY_DEFAULT_RULE_MODE_UNSUPPORTED,
    TRANS_KEY_DEFAULT_RULE_NOT_FOUND,
    TRANS_KEY_DEFAULT_RULE_UPDATE_FAILED,
    TRANS_KEY_ENTITY_PROFILE_DEFAULT_RULE,
    TRANS_KEY_ENTITY_PROFILE_FILTER_MODE,
    TRANS_KEY_ENTITY_PROFILE_OPTION,
    TRANS_KEY_ENTITY_PROFILE_RULE_GROUP,
    TRANS_KEY_ENTITY_PROFILE_SERVICE,
    TRANS_KEY_FILTER_MODE_UNSUPPORTED,
    TRANS_KEY_FILTER_MODE_UPDATE_FAILED,
    TRANS_KEY_FILTER_NOT_FOUND,
    TRANS_KEY_OPTION_NOT_FOUND,
    TRANS_KEY_OPTION_UPDATE_FAILED,
    TRANS_KEY_OPTION_VALUE_UNSUPPORTED,
    TRANS_KEY_RULE_GROUP_MODE_UNSUPPORTED,
    TRANS_KEY_RULE_GROUP_NOT_FOUND,
    TRANS_KEY_RULE_GROUP_UPDATE_FAILED,
    TRANS_KEY_SERVICE_MODE_UNSUPPORTED,
    TRANS_KEY_SERVICE_NOT_FOUND,
    TRANS_KEY_SERVICE_UPDATE_FAILED,
)
from .entity import ControlDManagerProfileEntity
from .models import (
    ControlDDefaultRule,
    ControlDFilter,
    ControlDManagerRuntime,
    ControlDProfileOption,
    ControlDRuleGroup,
    ControlDService,
    default_rule_mode_options,
    rule_group_mode_options,
    service_mode_options,
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
    if key.endswith("::default_rule"):
        _, profile_pk, _ = key.split("::", 2)
        return ControlDManagerProfileDefaultRuleSelect(config_entry, profile_pk)
    if "::rule_group::" in key:
        _, profile_pk, _, group_pk = key.split("::", 3)
        return ControlDManagerProfileRuleGroupSelect(config_entry, profile_pk, group_pk)
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
    if "::option::" in key:
        _, profile_pk, _, option_pk = key.split("::", 3)
        return ControlDManagerProfileOptionSelect(config_entry, profile_pk, option_pk)
    raise ValueError(f"Unsupported Control D select key {key!r}")


class ControlDManagerProfileFilterModeSelect(
    ControlDManagerProfileEntity, SelectEntity
):
    """Select surface for modal profile filters."""

    _attr_translation_key = TRANS_KEY_ENTITY_PROFILE_FILTER_MODE
    _purpose = PURPOSE_PROFILE_FILTER_MODE

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
            raise _ha_error(TRANS_KEY_FILTER_NOT_FOUND)
        selected_level = next(
            (level for level in filter_row.levels if level.title == option),
            None,
        )
        if selected_level is None:
            raise _ha_error(TRANS_KEY_FILTER_MODE_UNSUPPORTED)
        try:
            await self.runtime.managers.profile.async_set_filter_mode(
                self._profile_pk, self._filter_pk, selected_level.slug
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_FILTER_MODE_UPDATE_FAILED) from err


class ControlDManagerProfileServiceModeSelect(
    ControlDManagerProfileEntity, SelectEntity
):
    """Select surface for one dynamically exposed service."""

    _attr_translation_key = TRANS_KEY_ENTITY_PROFILE_SERVICE
    _purpose = PURPOSE_PROFILE_SERVICE

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

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Return live service metadata including redirect details."""
        attributes = dict(super().extra_state_attributes or {})
        service_row = self.service_row
        if service_row is None:
            return attributes or None
        if (redirect_target := service_row.redirect_target) is not None:
            attributes[ATTR_REDIRECT_TARGET] = redirect_target
        if (redirect_target_type := service_row.redirect_target_type) is not None:
            attributes[ATTR_REDIRECT_TARGET_TYPE] = redirect_target_type
        if service_row.unlock_location is not None:
            attributes[ATTR_SUGGESTED_REDIRECT_TARGET] = service_row.unlock_location
        return attributes or None

    def select_option(self, option: str) -> None:
        """Select option is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        """Set a new mode for the service."""
        service_row = self.service_row
        if service_row is None:
            raise _ha_error(TRANS_KEY_SERVICE_NOT_FOUND)
        if option not in service_mode_options():
            raise _ha_error(TRANS_KEY_SERVICE_MODE_UNSUPPORTED)
        try:
            await self.runtime.managers.profile.async_set_service_mode(
                self._profile_pk, self._service_pk, option
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_SERVICE_UPDATE_FAILED) from err


class ControlDManagerProfileDefaultRuleSelect(
    ControlDManagerProfileEntity, SelectEntity
):
    """Select surface for one profile default rule."""

    _attr_translation_key = TRANS_KEY_ENTITY_PROFILE_DEFAULT_RULE
    _purpose = PURPOSE_PROFILE_DEFAULT_RULE

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize one default-rule select."""
        super().__init__(config_entry, profile_pk, "default_rule")
        self._attr_name = "Options / Default Rule"
        self._attr_entity_registry_enabled_default = True

    @property
    def default_rule_row(self) -> ControlDDefaultRule | None:
        """Return the current normalized default-rule row."""
        return self.runtime.registry.default_rules_by_profile.get(self._profile_pk)

    @property
    def available(self) -> bool:
        """Return whether the default rule still exists in the registry."""
        return super().available and self.default_rule_row is not None

    @property
    def options(self) -> list[str]:
        """Return the supported default-rule labels."""
        return list(default_rule_mode_options())

    @property
    def current_option(self) -> str | None:
        """Return the current default-rule mode label."""
        default_rule_row = self.default_rule_row
        if default_rule_row is None:
            return None
        return default_rule_row.current_mode

    def select_option(self, option: str) -> None:
        """Select option is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        """Set a new default-rule mode for the profile."""
        if option not in default_rule_mode_options():
            raise _ha_error(TRANS_KEY_DEFAULT_RULE_MODE_UNSUPPORTED)
        if self.default_rule_row is None:
            raise _ha_error(TRANS_KEY_DEFAULT_RULE_NOT_FOUND)
        try:
            await self.runtime.managers.profile.async_set_default_rule_mode(
                self._profile_pk, option
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_DEFAULT_RULE_UPDATE_FAILED) from err


class ControlDManagerProfileRuleGroupSelect(ControlDManagerProfileEntity, SelectEntity):
    """Select surface for one exposed profile rule folder."""

    _attr_translation_key = TRANS_KEY_ENTITY_PROFILE_RULE_GROUP
    _purpose = PURPOSE_PROFILE_RULE_GROUP

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        group_pk: str,
    ) -> None:
        """Initialize one profile folder-rule select."""
        self._group_pk = group_pk
        super().__init__(config_entry, profile_pk, f"rule_group::{group_pk}")
        group_row = self.group_row
        self._attr_name = (
            f"Rules / Folder / {group_row.name}"
            if group_row is not None
            else f"Rules / Folder / {group_pk}"
        )
        self._attr_entity_registry_enabled_default = True

    @property
    def group_row(self) -> ControlDRuleGroup | None:
        """Return the current normalized folder row."""
        return self.runtime.registry.rule_groups_by_profile.get(
            self._profile_pk, {}
        ).get(self._group_pk)

    @property
    def available(self) -> bool:
        """Return whether the folder still exists in the registry."""
        return super().available and self.group_row is not None

    @property
    def options(self) -> list[str]:
        """Return the supported folder-rule option keys."""
        return list(rule_group_mode_options())

    @property
    def current_option(self) -> str | None:
        """Return the current folder-rule mode key."""
        group_row = self.group_row
        if group_row is None:
            return None
        return group_row.current_mode

    def select_option(self, option: str) -> None:
        """Select option is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        """Set a new folder-rule mode for the profile."""
        if option not in rule_group_mode_options():
            raise _ha_error(TRANS_KEY_RULE_GROUP_MODE_UNSUPPORTED)
        if self.group_row is None:
            raise _ha_error(TRANS_KEY_RULE_GROUP_NOT_FOUND)
        try:
            await self.runtime.managers.profile.async_set_rule_group_mode(
                self._profile_pk, self._group_pk, option
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_RULE_GROUP_UPDATE_FAILED) from err


class ControlDManagerProfileOptionSelect(ControlDManagerProfileEntity, SelectEntity):
    """Select surface for one profile option."""

    _attr_translation_key = TRANS_KEY_ENTITY_PROFILE_OPTION
    _purpose = PURPOSE_PROFILE_OPTION

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
        option_pk: str,
    ) -> None:
        """Initialize one profile option select."""
        self._option_pk = option_pk
        super().__init__(config_entry, profile_pk, f"option::{option_pk}")
        option_row = self.option_row
        self._attr_name = (
            f"Options / {option_row.title}"
            if option_row is not None
            else f"Options / {option_pk}"
        )
        self._attr_entity_registry_enabled_default = option_pk == "ai_malware"

    @property
    def option_row(self) -> ControlDProfileOption | None:
        """Return the current normalized profile option row."""
        return self.runtime.registry.options_by_profile.get(self._profile_pk, {}).get(
            self._option_pk
        )

    @property
    def available(self) -> bool:
        """Return whether the option still exists and supports select behavior."""
        option_row = self.option_row
        return bool(
            super().available
            and option_row is not None
            and option_row.entity_kind == "select"
        )

    @property
    def options(self) -> list[str]:
        """Return the supported option labels."""
        option_row = self.option_row
        if option_row is None:
            return []
        return list(option_row.select_options)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option label."""
        option_row = self.option_row
        if option_row is None:
            return None
        return option_row.current_select_option

    def select_option(self, option: str) -> None:
        """Select option is handled asynchronously by Home Assistant."""
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        """Set a new value for the profile option."""
        option_row = self.option_row
        if option_row is None:
            raise _ha_error(TRANS_KEY_OPTION_NOT_FOUND)
        if option not in option_row.select_options:
            raise _ha_error(TRANS_KEY_OPTION_VALUE_UNSUPPORTED)
        try:
            await self.runtime.managers.profile.async_set_profile_option_select(
                self._profile_pk, self._option_pk, option
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_OPTION_UPDATE_FAILED) from err
