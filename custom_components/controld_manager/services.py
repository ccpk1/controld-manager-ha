"""Shared Home Assistant services for Control D Manager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from .const import (
    DEFAULT_DISABLE_MINUTES,
    DOMAIN,
    SERVICE_CREATE_RULE,
    SERVICE_DELETE_RULE,
    SERVICE_DISABLE_PROFILE,
    SERVICE_ENABLE_PROFILE,
    SERVICE_FIELD_CANCEL_EXPIRATION,
    SERVICE_FIELD_CATALOG_TYPE,
    SERVICE_FIELD_COMMENT,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_EXPIRATION_DURATION,
    SERVICE_FIELD_EXPIRE_AT,
    SERVICE_FIELD_FILTER_ID,
    SERVICE_FIELD_FILTER_NAME,
    SERVICE_FIELD_HOSTNAME,
    SERVICE_FIELD_MINUTES,
    SERVICE_FIELD_MODE,
    SERVICE_FIELD_OPTION_ID,
    SERVICE_FIELD_OPTION_NAME,
    SERVICE_FIELD_PROFILE_ID,
    SERVICE_FIELD_PROFILE_NAME,
    SERVICE_FIELD_RULE_GROUP_ID,
    SERVICE_FIELD_RULE_GROUP_NAME,
    SERVICE_FIELD_RULE_IDENTITY,
    SERVICE_FIELD_SERVICE_ID,
    SERVICE_FIELD_SERVICE_NAME,
    SERVICE_FIELD_VALUE,
    SERVICE_GET_CATALOG,
    SERVICE_SET_DEFAULT_RULE_STATE,
    SERVICE_SET_FILTER_STATE,
    SERVICE_SET_OPTION_STATE,
    SERVICE_SET_RULE_STATE,
    SERVICE_SET_SERVICE_STATE,
    TRANS_KEY_CONFIG_ENTRY_NAME_AMBIGUOUS,
    TRANS_KEY_CONFIG_ENTRY_NAME_NOT_FOUND,
    TRANS_KEY_CONFIG_ENTRY_NOT_FOUND,
    TRANS_KEY_CONFIG_ENTRY_NOT_LOADED,
    TRANS_KEY_CREATE_RULES_FAILED,
    TRANS_KEY_DELETE_RULES_FAILED,
    TRANS_KEY_DISABLE_PROFILES_FAILED,
    TRANS_KEY_ENABLE_PROFILES_FAILED,
    TRANS_KEY_MULTIPLE_ENTRIES_LOADED,
    TRANS_KEY_OPTION_MUTATION_REQUIRED,
    TRANS_KEY_OPTION_VALUE_UNSUPPORTED,
    TRANS_KEY_PROFILE_TARGET_AMBIGUOUS,
    TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
    TRANS_KEY_PROFILE_TARGET_REQUIRED,
    TRANS_KEY_RULE_ALREADY_EXISTS,
    TRANS_KEY_RULE_GROUP_NAME_AMBIGUOUS,
    TRANS_KEY_RULE_GROUP_NAME_NOT_FOUND,
    TRANS_KEY_RULE_HOSTNAME_DUPLICATE,
    TRANS_KEY_RULE_HOSTNAME_REQUIRED,
    TRANS_KEY_RULE_MUTATION_REQUIRED,
    TRANS_KEY_SERVICE_MODE_REJECTED,
    TRANS_KEY_SET_DEFAULT_RULES_FAILED,
    TRANS_KEY_SET_FILTERS_FAILED,
    TRANS_KEY_SET_OPTIONS_FAILED,
    TRANS_KEY_SET_RULES_FAILED,
    TRANS_KEY_SET_SERVICES_FAILED,
    TRANS_KEY_WRONG_INTEGRATION_ENTRY,
)
from .models import (
    ControlDManagerRuntime,
    ControlDService,
    default_rule_mode_labels,
    rule_action_options,
    service_mode_labels,
)
from .service_selectors import (
    _normalize_name,
    _resolve_selected_filter_pks,
    _resolve_selected_option_pks,
    _resolve_selected_rule_identities,
    _resolve_selected_service_pks,
)

ControlDManagerConfigEntry = ConfigEntry[ControlDManagerRuntime]


def _ha_error(translation_key: str) -> HomeAssistantError:
    """Build one translated Home Assistant error."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=translation_key,
    )


CATALOG_TYPES: tuple[str, ...] = (
    "filters",
    "services",
    "rules",
    "profile_options",
)

_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS: dict[vol.Marker, object] = {
    vol.Optional(SERVICE_FIELD_PROFILE_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(SERVICE_FIELD_PROFILE_NAME): vol.Any(cv.string, [cv.string]),
}

_FILTER_SERVICE_EXPLICIT_SELECTOR_FIELDS: dict[vol.Marker, object] = {
    vol.Optional(SERVICE_FIELD_FILTER_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(SERVICE_FIELD_FILTER_NAME): vol.Any(cv.string, [cv.string]),
}

_SERVICE_SERVICE_EXPLICIT_SELECTOR_FIELDS: dict[vol.Marker, object] = {
    vol.Optional(SERVICE_FIELD_SERVICE_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(SERVICE_FIELD_SERVICE_NAME): vol.Any(cv.string, [cv.string]),
}

_OPTION_SERVICE_EXPLICIT_SELECTOR_FIELDS: dict[vol.Marker, object] = {
    vol.Optional(SERVICE_FIELD_OPTION_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(SERVICE_FIELD_OPTION_NAME): vol.Any(cv.string, [cv.string]),
}

_RULE_SERVICE_EXPLICIT_SELECTOR_FIELDS: dict[vol.Marker, object] = {
    vol.Optional(SERVICE_FIELD_RULE_IDENTITY): vol.Any(cv.string, [cv.string]),
}

_RULE_GROUP_SERVICE_EXPLICIT_SELECTOR_FIELDS: dict[vol.Marker, object] = {
    vol.Optional(SERVICE_FIELD_RULE_GROUP_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(SERVICE_FIELD_RULE_GROUP_NAME): vol.Any(cv.string, [cv.string]),
}

_PROFILE_SERVICE_ENTRY_TARGET_FIELDS: dict[vol.Marker, object] = {
    vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
}

DISABLE_PROFILE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Optional(
            SERVICE_FIELD_MINUTES, default=DEFAULT_DISABLE_MINUTES
        ): cv.positive_int,
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

ENABLE_PROFILE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

SET_FILTER_STATE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_FILTER_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Required(SERVICE_FIELD_ENABLED): cv.boolean,
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

SET_SERVICE_STATE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_SERVICE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Required(SERVICE_FIELD_MODE): vol.In(service_mode_labels()),
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

SET_OPTION_STATE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_OPTION_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Optional(SERVICE_FIELD_ENABLED): cv.boolean,
        vol.Optional(SERVICE_FIELD_VALUE): vol.Any(cv.string, cv.positive_int),
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

SET_DEFAULT_RULE_STATE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Required(SERVICE_FIELD_MODE): vol.In(default_rule_mode_labels()),
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

SET_RULE_STATE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_RULE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Optional(SERVICE_FIELD_ENABLED): cv.boolean,
        vol.Optional(SERVICE_FIELD_MODE): vol.In(rule_action_options()),
        vol.Optional(SERVICE_FIELD_COMMENT): cv.string,
        vol.Optional(SERVICE_FIELD_CANCEL_EXPIRATION): cv.boolean,
        vol.Optional(SERVICE_FIELD_EXPIRATION_DURATION): vol.All(
            cv.time_period,
            vol.Range(min=timedelta(seconds=1)),
        ),
        vol.Optional(SERVICE_FIELD_EXPIRE_AT): cv.datetime,
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

CREATE_RULE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Required(SERVICE_FIELD_HOSTNAME): vol.Any(cv.string, [cv.string]),
        **_RULE_GROUP_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        vol.Optional(SERVICE_FIELD_ENABLED): cv.boolean,
        vol.Optional(SERVICE_FIELD_MODE): vol.In(rule_action_options()),
        vol.Optional(SERVICE_FIELD_COMMENT): cv.string,
        vol.Optional(SERVICE_FIELD_EXPIRATION_DURATION): vol.All(
            cv.time_period,
            vol.Range(min=timedelta(seconds=1)),
        ),
        vol.Optional(SERVICE_FIELD_EXPIRE_AT): cv.datetime,
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

DELETE_RULE_SERVICE_SCHEMA = vol.Schema(
    {
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_RULE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)

GET_CATALOG_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_FIELD_CATALOG_TYPE): vol.In(CATALOG_TYPES),
        **_PROFILE_SERVICE_EXPLICIT_SELECTOR_FIELDS,
        **_PROFILE_SERVICE_ENTRY_TARGET_FIELDS,
    }
)


@dataclass(frozen=True, slots=True)
class ResolvedProfileServiceTarget:
    """Resolved service target for a profile mutation."""

    entry: ControlDManagerConfigEntry
    profile_pks: frozenset[str]


@dataclass(frozen=True, slots=True)
class ResolvedFilterServiceTarget:
    """Resolved service target for a profile-filter mutation."""

    entry: ControlDManagerConfigEntry
    profile_filters: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class ResolvedCatalogServiceTarget:
    """Resolved service target for a read-only catalog response."""

    entry: ControlDManagerConfigEntry
    profile_pks: frozenset[str]
    catalog_type: str


@dataclass(frozen=True, slots=True)
class ResolvedRuleServiceTarget:
    """Resolved service target for a profile-rule mutation."""

    entry: ControlDManagerConfigEntry
    profile_rules: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class ResolvedServiceServiceTarget:
    """Resolved service target for a profile-service mutation."""

    entry: ControlDManagerConfigEntry
    profile_services: dict[str, frozenset[str]]
    service_rows_by_profile: dict[str, dict[str, ControlDService]] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedOptionServiceTarget:
    """Resolved service target for a profile-option mutation."""

    entry: ControlDManagerConfigEntry
    profile_options: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class ResolvedCreateRuleServiceTarget:
    """Resolved service target for a profile-rule creation request."""

    entry: ControlDManagerConfigEntry
    profile_pks: frozenset[str]
    rule_group_by_profile: dict[str, str | None]
    rule_group_name_by_profile: dict[str, str | None]
    existing_hostnames_by_profile: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class ParsedRuleMutation:
    """Normalized mutation values for a rule-state service call."""

    enabled: bool | None
    mode: str | None
    comment: str | None
    ttl: int | None


async def async_register_services(hass: HomeAssistant) -> None:
    """Register shared Control D services."""

    async def async_handle_disable_profile(call: ServiceCall) -> None:
        """Disable targeted profiles for the requested duration."""
        resolved_target = _resolve_profile_service_target(
            hass,
            call,
            allow_entity_ids=False,
            allow_profile_names=True,
            profile_device_field=SERVICE_FIELD_PROFILE_ID,
            require_profile_selector=True,
        )
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_disable_profiles(
                set(resolved_target.profile_pks),
                call.data[SERVICE_FIELD_MINUTES],
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_DISABLE_PROFILES_FAILED) from err

    async def async_handle_enable_profile(call: ServiceCall) -> None:
        """Enable targeted profiles immediately."""
        resolved_target = _resolve_profile_service_target(
            hass,
            call,
            allow_entity_ids=False,
            allow_profile_names=True,
            profile_device_field=SERVICE_FIELD_PROFILE_ID,
            require_profile_selector=True,
        )
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_enable_profiles(
                set(resolved_target.profile_pks)
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_ENABLE_PROFILES_FAILED) from err

    async def async_handle_set_filter_state(call: ServiceCall) -> None:
        """Enable or disable one named filter across targeted profiles."""
        resolved_target = _resolve_filter_service_target(hass, call)
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_set_filters_enabled(
                resolved_target.profile_filters,
                call.data[SERVICE_FIELD_ENABLED],
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_SET_FILTERS_FAILED) from err

    async def async_handle_set_rule_state(call: ServiceCall) -> None:
        """Enable or disable one or more targeted Control D rules."""
        mutation = _parse_rule_mutation(call)
        _require_rule_mutation(mutation)
        resolved_target = _resolve_rule_service_target(hass, call)
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_set_rules_state(
                resolved_target.profile_rules,
                enabled=mutation.enabled,
                mode=mutation.mode,
                ttl=mutation.ttl,
                comment=mutation.comment,
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_SET_RULES_FAILED) from err

    async def async_handle_create_rule(call: ServiceCall) -> None:
        """Create one or more Control D rules across the selected profiles."""
        mutation = _parse_rule_mutation(call)
        resolved_target = await _resolve_create_rule_service_target(hass, call)
        hostnames = _resolve_rule_hostnames(call)
        _validate_rule_creates(
            resolved_target.existing_hostnames_by_profile,
            hostnames,
        )
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_create_rules(
                resolved_target.profile_pks,
                hostnames=hostnames,
                group_pks_by_profile=resolved_target.rule_group_by_profile,
                group_names_by_profile=resolved_target.rule_group_name_by_profile,
                enabled=mutation.enabled,
                mode=mutation.mode,
                ttl=mutation.ttl,
                comment=mutation.comment,
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_CREATE_RULES_FAILED) from err

    async def async_handle_delete_rule(call: ServiceCall) -> None:
        """Delete one or more targeted Control D rules."""
        resolved_target = _resolve_rule_service_target(hass, call)
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_delete_rules(resolved_target.profile_rules)
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_DELETE_RULES_FAILED) from err

    async def async_handle_set_service_state(call: ServiceCall) -> None:
        """Set one or more targeted Control D services to the requested mode."""
        resolved_target = await _resolve_service_service_target(hass, call)
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_set_services_mode(
                resolved_target.profile_services,
                call.data[SERVICE_FIELD_MODE],
                service_rows_by_profile=resolved_target.service_rows_by_profile,
            )
        except ControlDApiResponseError as err:
            raise _ha_error(TRANS_KEY_SERVICE_MODE_REJECTED) from err
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
        ) as err:
            raise _ha_error(TRANS_KEY_SET_SERVICES_FAILED) from err

    async def async_handle_set_option_state(call: ServiceCall) -> None:
        """Set one or more targeted Control D options across selected profiles."""
        enabled = call.data.get(SERVICE_FIELD_ENABLED)
        value = call.data.get(SERVICE_FIELD_VALUE)
        resolved_target = _resolve_option_service_target(hass, call)
        normalized_value = _validate_option_mutation(
            resolved_target.entry,
            resolved_target.profile_options,
            enabled=enabled,
            value=value,
        )
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_set_profile_options_state(
                resolved_target.profile_options,
                enabled=enabled,
                value=normalized_value,
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_SET_OPTIONS_FAILED) from err

    async def async_handle_set_default_rule_state(call: ServiceCall) -> None:
        """Set the default-rule mode across one or more targeted profiles."""
        resolved_target = _resolve_profile_service_target(
            hass,
            call,
            allow_entity_ids=False,
            allow_profile_names=True,
            profile_device_field=SERVICE_FIELD_PROFILE_ID,
            require_profile_selector=True,
        )
        try:
            profile_manager = resolved_target.entry.runtime_data.managers.profile
            await profile_manager.async_set_default_rules_mode(
                resolved_target.profile_pks,
                call.data[SERVICE_FIELD_MODE],
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise _ha_error(TRANS_KEY_SET_DEFAULT_RULES_FAILED) from err

    async def async_handle_get_catalog(call: ServiceCall) -> ServiceResponse:
        """Return a typed catalog response for one config entry scope."""
        resolved_target = _resolve_catalog_service_target(hass, call)
        integration_manager = resolved_target.entry.runtime_data.managers.integration
        return await integration_manager.async_build_catalog_response(
            config_entry_id=resolved_target.entry.entry_id,
            catalog_type=resolved_target.catalog_type,
            profile_pks=resolved_target.profile_pks,
        )

    for legacy_service in ("pause_profile", "resume_profile", "set_filter_enabled"):
        if hass.services.has_service(DOMAIN, legacy_service):
            hass.services.async_remove(DOMAIN, legacy_service)

    if not hass.services.has_service(DOMAIN, SERVICE_DISABLE_PROFILE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DISABLE_PROFILE,
            async_handle_disable_profile,
            schema=DISABLE_PROFILE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ENABLE_PROFILE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ENABLE_PROFILE,
            async_handle_enable_profile,
            schema=ENABLE_PROFILE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_FILTER_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_FILTER_STATE,
            async_handle_set_filter_state,
            schema=SET_FILTER_STATE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_RULE_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            async_handle_set_rule_state,
            schema=SET_RULE_STATE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_RULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CREATE_RULE,
            async_handle_create_rule,
            schema=CREATE_RULE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_RULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_RULE,
            async_handle_delete_rule,
            schema=DELETE_RULE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_SERVICE_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SERVICE_STATE,
            async_handle_set_service_state,
            schema=SET_SERVICE_STATE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_OPTION_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_OPTION_STATE,
            async_handle_set_option_state,
            schema=SET_OPTION_STATE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_DEFAULT_RULE_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_DEFAULT_RULE_STATE,
            async_handle_set_default_rule_state,
            schema=SET_DEFAULT_RULE_STATE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_CATALOG):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_CATALOG,
            async_handle_get_catalog,
            schema=GET_CATALOG_SERVICE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )


def _resolve_filter_service_target(
    hass: HomeAssistant, call: ServiceCall
) -> ResolvedFilterServiceTarget:
    """Resolve a filter mutation target across one or more profiles."""
    resolved_profiles = _resolve_profile_service_target(
        hass,
        call,
        allow_entity_ids=False,
        allow_profile_names=True,
        profile_device_field=SERVICE_FIELD_PROFILE_ID,
        require_profile_selector=True,
    )
    requested_filter_ids = _ensure_name_list(call.data.get(SERVICE_FIELD_FILTER_ID))
    requested_filter_names = _ensure_name_list(call.data.get(SERVICE_FIELD_FILTER_NAME))
    profile_filters = _resolve_selected_filter_pks(
        resolved_profiles.entry,
        resolved_profiles.profile_pks,
        requested_filter_ids=requested_filter_ids,
        requested_filter_names=requested_filter_names,
    )
    return ResolvedFilterServiceTarget(
        entry=resolved_profiles.entry,
        profile_filters=profile_filters,
    )


def _resolve_catalog_service_target(
    hass: HomeAssistant, call: ServiceCall
) -> ResolvedCatalogServiceTarget:
    """Resolve a read-only catalog request into one entry and profile scope."""
    resolved_profiles = _resolve_profile_service_target(
        hass,
        call,
        allow_entity_ids=False,
        allow_profile_names=True,
        profile_device_field=SERVICE_FIELD_PROFILE_ID,
        require_profile_selector=False,
    )
    catalog_type = call.data[SERVICE_FIELD_CATALOG_TYPE]
    return ResolvedCatalogServiceTarget(
        entry=resolved_profiles.entry,
        profile_pks=resolved_profiles.profile_pks,
        catalog_type=catalog_type,
    )


def _resolve_option_service_target(
    hass: HomeAssistant, call: ServiceCall
) -> ResolvedOptionServiceTarget:
    """Resolve an option mutation target across one or more profiles."""
    resolved_profiles = _resolve_profile_service_target(
        hass,
        call,
        allow_entity_ids=False,
        allow_profile_names=True,
        profile_device_field=SERVICE_FIELD_PROFILE_ID,
        require_profile_selector=True,
    )
    requested_option_ids = _ensure_name_list(call.data.get(SERVICE_FIELD_OPTION_ID))
    requested_option_names = _ensure_name_list(call.data.get(SERVICE_FIELD_OPTION_NAME))
    profile_options = _resolve_selected_option_pks(
        resolved_profiles.entry,
        resolved_profiles.profile_pks,
        requested_option_ids=requested_option_ids,
        requested_option_titles=requested_option_names,
    )
    return ResolvedOptionServiceTarget(
        entry=resolved_profiles.entry,
        profile_options=profile_options,
    )


async def _resolve_create_rule_service_target(
    hass: HomeAssistant, call: ServiceCall
) -> ResolvedCreateRuleServiceTarget:
    """Resolve a rule-creation target across one or more profiles."""
    resolved_profiles = _resolve_profile_service_target(
        hass,
        call,
        allow_entity_ids=False,
        allow_profile_names=True,
        profile_device_field=SERVICE_FIELD_PROFILE_ID,
        require_profile_selector=True,
    )
    requested_group_ids = _ensure_name_list(call.data.get(SERVICE_FIELD_RULE_GROUP_ID))
    requested_group_names = _ensure_name_list(
        call.data.get(SERVICE_FIELD_RULE_GROUP_NAME)
    )
    live_rule_catalog = await _async_load_rules_for_resolution(
        resolved_profiles.entry,
        resolved_profiles.profile_pks,
    )
    if len(requested_group_ids) > 1 or len(requested_group_names) > 1:
        raise ServiceValidationError(
            "The selected Control D rule-group target is ambiguous",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_RULE_GROUP_NAME_AMBIGUOUS,
        )
    if not requested_group_ids and not requested_group_names:
        return ResolvedCreateRuleServiceTarget(
            entry=resolved_profiles.entry,
            profile_pks=resolved_profiles.profile_pks,
            rule_group_by_profile=dict.fromkeys(resolved_profiles.profile_pks, None),
            rule_group_name_by_profile=dict.fromkeys(
                resolved_profiles.profile_pks, None
            ),
            existing_hostnames_by_profile={
                profile_pk: frozenset(
                    rule_row.rule_pk.removesuffix(".").casefold()
                    for rule_row in rules_by_profile.values()
                )
                for profile_pk, (_, rules_by_profile) in live_rule_catalog.items()
            },
        )
    matched_value = (
        requested_group_ids[0] if requested_group_ids else requested_group_names[0]
    )
    normalized_match = _normalize_name(matched_value)
    return ResolvedCreateRuleServiceTarget(
        entry=resolved_profiles.entry,
        profile_pks=resolved_profiles.profile_pks,
        rule_group_by_profile={
            profile_pk: _resolve_live_rule_group_pk(
                live_rule_catalog[profile_pk][0],
                normalized_match,
                use_ids=bool(requested_group_ids),
            )
            for profile_pk in resolved_profiles.profile_pks
        },
        rule_group_name_by_profile={
            profile_pk: live_rule_catalog[profile_pk][0][
                _resolve_live_rule_group_pk(
                    live_rule_catalog[profile_pk][0],
                    normalized_match,
                    use_ids=bool(requested_group_ids),
                )
            ].name
            for profile_pk in resolved_profiles.profile_pks
        },
        existing_hostnames_by_profile={
            profile_pk: frozenset(
                rule_row.rule_pk.removesuffix(".").casefold()
                for rule_row in rules_by_profile.values()
            )
            for profile_pk, (_, rules_by_profile) in live_rule_catalog.items()
        },
    )


def _parse_rule_mutation(call: ServiceCall) -> ParsedRuleMutation:
    """Normalize the supported rule-mutation fields for service handlers."""
    enabled = call.data.get(SERVICE_FIELD_ENABLED)
    mode = call.data.get(SERVICE_FIELD_MODE)
    comment = call.data.get(SERVICE_FIELD_COMMENT)
    cancel_expiration = call.data.get(SERVICE_FIELD_CANCEL_EXPIRATION, False)
    expiration_duration = call.data.get(SERVICE_FIELD_EXPIRATION_DURATION)
    expire_at = call.data.get(SERVICE_FIELD_EXPIRE_AT)
    expires_at: int | None = None
    if cancel_expiration:
        expires_at = -1
    elif expiration_duration is not None:
        expires_at = int((dt_util.utcnow() + expiration_duration).timestamp())
    if not cancel_expiration and expire_at is not None:
        expires_at = int(dt_util.as_utc(expire_at).timestamp())

    return ParsedRuleMutation(
        enabled=enabled,
        mode=mode,
        comment=comment,
        ttl=expires_at,
    )


def _require_rule_mutation(mutation: ParsedRuleMutation) -> None:
    """Require at least one explicit rule mutation field."""
    if (
        mutation.enabled is None
        and mutation.mode is None
        and mutation.comment is None
        and mutation.ttl is None
    ):
        raise ServiceValidationError(
            "Provide at least one rule mutation field",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_RULE_MUTATION_REQUIRED,
        )


def _resolve_rule_hostnames(call: ServiceCall) -> tuple[str, ...]:
    """Normalize the requested create-rule hostnames from one service call."""
    raw_values = _ensure_name_list(call.data.get(SERVICE_FIELD_HOSTNAME))
    if not raw_values:
        raise ServiceValidationError(
            "Select at least one Control D rule hostname",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_RULE_HOSTNAME_REQUIRED,
        )

    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for raw_value in raw_values:
        hostname = raw_value.strip().removesuffix(".")
        if not hostname:
            continue
        normalized_hostname = hostname.casefold()
        if normalized_hostname in seen_values:
            raise ServiceValidationError(
                "The selected Control D rule hostname is duplicated",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_RULE_HOSTNAME_DUPLICATE,
            )
        seen_values.add(normalized_hostname)
        normalized_values.append(hostname)

    if not normalized_values:
        raise ServiceValidationError(
            "Select at least one Control D rule hostname",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_RULE_HOSTNAME_REQUIRED,
        )
    return tuple(normalized_values)


async def _async_load_rules_for_resolution(
    entry: ControlDManagerConfigEntry,
    profile_pks: frozenset[str],
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """Load live rule-group and rule rows for targeted profiles."""
    integration_manager = entry.runtime_data.managers.integration
    profile_details = await asyncio.gather(
        *(
            entry.runtime_data.client.async_get_profile_detail(
                profile_pk,
                include_services=False,
                include_rules=True,
            )
            for profile_pk in profile_pks
        )
    )
    return {
        profile_pk: (
            integration_manager._normalize_rule_groups(detail.groups),
            integration_manager._normalize_rules(detail.groups, detail.rules),
        )
        for profile_pk, detail in zip(profile_pks, profile_details, strict=True)
    }


def _resolve_live_rule_group_pk(
    groups_by_profile: dict[str, Any],
    normalized_match: str,
    *,
    use_ids: bool,
) -> str:
    """Resolve one live rule-group selector for one profile."""
    matches = [
        group_pk
        for group_pk, group_row in groups_by_profile.items()
        if _normalize_name(group_pk if use_ids else group_row.name) == normalized_match
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ServiceValidationError(
            "The selected Control D rule-group target is ambiguous",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_RULE_GROUP_NAME_AMBIGUOUS,
        )
    raise ServiceValidationError(
        (
            "The selected Control D rule-group target could not be resolved "
            "for one or more targeted profiles"
        ),
        translation_domain=DOMAIN,
        translation_key=TRANS_KEY_RULE_GROUP_NAME_NOT_FOUND,
    )


def _validate_rule_creates(
    existing_hostnames_by_profile: dict[str, frozenset[str]],
    hostnames: tuple[str, ...],
) -> None:
    """Reject duplicate rule creates before calling the upstream API."""
    normalized_requested = {hostname.casefold() for hostname in hostnames}
    for existing_hostnames in existing_hostnames_by_profile.values():
        if normalized_requested & existing_hostnames:
            raise ServiceValidationError(
                (
                    "The selected Control D rule hostname already exists for "
                    "one or more targeted profiles"
                ),
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_RULE_ALREADY_EXISTS,
            )


def _validate_option_mutation(
    entry: ControlDManagerConfigEntry,
    profile_options: dict[str, frozenset[str]],
    *,
    enabled: bool | None,
    value: str | int | None,
) -> str | None:
    """Validate that the requested option mutation fits the targeted options."""
    if enabled is None and value is None:
        raise ServiceValidationError(
            "Provide at least one option mutation field",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_OPTION_MUTATION_REQUIRED,
        )

    normalized_value: str | None = None

    for profile_pk, option_pks in profile_options.items():
        for option_pk in option_pks:
            option_row = entry.runtime_data.registry.options_by_profile[profile_pk][
                option_pk
            ]
            if option_row.option_type == "field" and option_row.option_pk in {
                "ttl_blck",
                "ttl_spff",
                "ttl_pass",
            }:
                if value is not None:
                    if enabled is False:
                        raise ServiceValidationError(
                            (
                                "The selected numeric Control D options do not "
                                "accept Value when Enabled is false"
                            ),
                            translation_domain=DOMAIN,
                            translation_key=TRANS_KEY_OPTION_MUTATION_REQUIRED,
                        )
                    normalized_value = _normalize_field_option_value(value)
                    continue
                if enabled is None:
                    raise ServiceValidationError(
                        (
                            "The selected numeric Control D options require "
                            "Enabled or Value"
                        ),
                        translation_domain=DOMAIN,
                        translation_key=TRANS_KEY_OPTION_MUTATION_REQUIRED,
                    )
                continue
            if option_row.entity_kind == "toggle":
                if enabled is None:
                    raise ServiceValidationError(
                        (
                            "The selected toggle-style Control D options require "
                            "the Enabled field"
                        ),
                        translation_domain=DOMAIN,
                        translation_key=TRANS_KEY_OPTION_MUTATION_REQUIRED,
                    )
                continue
            if option_row.entity_kind == "select":
                if value is None:
                    if enabled is False:
                        continue
                    if enabled is True and (
                        option_row.default_value_key is not None or option_row.choices
                    ):
                        continue
                    raise ServiceValidationError(
                        (
                            "The selected select-style Control D options require "
                            "the Value field unless you are turning them off or "
                            "re-enabling them with the default value"
                        ),
                        translation_domain=DOMAIN,
                        translation_key=TRANS_KEY_OPTION_MUTATION_REQUIRED,
                    )
                if option_row.choice_value_for_input(str(value)) is None:
                    raise ServiceValidationError(
                        "The selected Control D option value is not supported",
                        translation_domain=DOMAIN,
                        translation_key=TRANS_KEY_OPTION_VALUE_UNSUPPORTED,
                    )
                continue
            raise ServiceValidationError(
                (
                    "The selected Control D options do not support Home "
                    "Assistant mutations"
                ),
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_OPTION_MUTATION_REQUIRED,
            )

    if normalized_value is not None:
        return normalized_value
    return str(value) if isinstance(value, int) else value


def _normalize_field_option_value(value: str | int) -> str:
    """Normalize one numeric field-option value from a service payload."""
    normalized_value = str(value).strip()
    try:
        numeric_value = int(normalized_value)
    except ValueError as err:
        raise ServiceValidationError(
            "The selected Control D option value is not supported",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_OPTION_VALUE_UNSUPPORTED,
        ) from err
    if numeric_value <= 0:
        raise ServiceValidationError(
            "The selected Control D option value is not supported",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_OPTION_VALUE_UNSUPPORTED,
        )
    return str(numeric_value)


def _resolve_rule_service_target(
    hass: HomeAssistant, call: ServiceCall
) -> ResolvedRuleServiceTarget:
    """Resolve a rule mutation target across one or more profiles."""
    resolved_profiles = _resolve_profile_service_target(
        hass,
        call,
        allow_entity_ids=False,
        allow_profile_names=True,
        profile_device_field=SERVICE_FIELD_PROFILE_ID,
        require_profile_selector=True,
    )
    requested_rule_identities = _ensure_name_list(
        call.data.get(SERVICE_FIELD_RULE_IDENTITY)
    )
    profile_rules = _resolve_selected_rule_identities(
        resolved_profiles.entry,
        resolved_profiles.profile_pks,
        requested_rule_identities=requested_rule_identities,
    )
    return ResolvedRuleServiceTarget(
        entry=resolved_profiles.entry,
        profile_rules=profile_rules,
    )


async def _resolve_service_service_target(
    hass: HomeAssistant, call: ServiceCall
) -> ResolvedServiceServiceTarget:
    """Resolve a service-mode mutation target across one or more profiles."""
    resolved_profiles = _resolve_profile_service_target(
        hass,
        call,
        allow_entity_ids=False,
        allow_profile_names=True,
        profile_device_field=SERVICE_FIELD_PROFILE_ID,
        require_profile_selector=True,
    )
    requested_service_ids = _ensure_name_list(call.data.get(SERVICE_FIELD_SERVICE_ID))
    requested_service_names = _ensure_name_list(
        call.data.get(SERVICE_FIELD_SERVICE_NAME)
    )
    if not requested_service_ids and not requested_service_names:
        profile_services = _resolve_selected_service_pks(
            resolved_profiles.entry,
            resolved_profiles.profile_pks,
            requested_service_ids=requested_service_ids,
            requested_service_names=requested_service_names,
        )
        return ResolvedServiceServiceTarget(
            entry=resolved_profiles.entry,
            profile_services=profile_services,
        )
    try:
        profile_services = _resolve_selected_service_pks(
            resolved_profiles.entry,
            resolved_profiles.profile_pks,
            requested_service_ids=requested_service_ids,
            requested_service_names=requested_service_names,
        )
        return ResolvedServiceServiceTarget(
            entry=resolved_profiles.entry,
            profile_services=profile_services,
        )
    except ServiceValidationError as err:
        live_services_by_profile = await _async_load_services_for_resolution(
            resolved_profiles.entry,
            resolved_profiles.profile_pks,
        )
        try:
            profile_services = _resolve_selected_service_pks_from_rows(
                live_services_by_profile,
                resolved_profiles.profile_pks,
                requested_service_ids=requested_service_ids,
                requested_service_names=requested_service_names,
            )
        except ServiceValidationError as live_err:
            raise err from live_err
        return ResolvedServiceServiceTarget(
            entry=resolved_profiles.entry,
            profile_services=profile_services,
            service_rows_by_profile=live_services_by_profile,
        )


async def _async_load_services_for_resolution(
    entry: ControlDManagerConfigEntry,
    profile_pks: frozenset[str],
) -> dict[str, dict[str, ControlDService]]:
    """Load service rows for targeted profiles without changing entity policy."""
    integration_manager = entry.runtime_data.managers.integration
    service_categories_payload = tuple(
        await entry.runtime_data.client.async_get_service_categories()
    )
    service_catalog_payload = tuple(
        await entry.runtime_data.client.async_get_service_catalog()
    )
    profile_services: dict[str, dict[str, ControlDService]] = {}
    for profile_pk in profile_pks:
        services_payload = tuple(
            await entry.runtime_data.client.async_get_profile_services(profile_pk)
        )
        profile_services[profile_pk] = integration_manager.build_live_service_rows(
            services_payload,
            service_categories_payload,
            service_catalog_payload,
        )
    return profile_services


def _resolve_selected_service_pks_from_rows(
    services_by_profile: dict[str, dict[str, ControlDService]],
    profile_pks: frozenset[str],
    *,
    requested_service_ids: list[str],
    requested_service_names: list[str],
) -> dict[str, frozenset[str]]:
    """Resolve service selectors from explicitly supplied normalized rows."""
    profile_services: dict[str, frozenset[str]] = {}

    if requested_service_ids:
        requested_values = requested_service_ids

        def value_getter(service_row: ControlDService) -> str:
            return service_row.service_pk

    else:
        requested_values = requested_service_names

        def value_getter(service_row: ControlDService) -> str:
            return service_row.name

    for profile_pk in profile_pks:
        resolved_service_ids: set[str] = set()
        services = tuple(services_by_profile.get(profile_pk, {}).values())
        for requested_value in requested_values:
            normalized_requested_value = _normalize_name(requested_value)
            matches = [
                service_row.service_pk
                for service_row in services
                if _normalize_name(value_getter(service_row))
                == normalized_requested_value
            ]
            if len(matches) == 1:
                resolved_service_ids.add(matches[0])
                continue
            if len(matches) > 1:
                raise ServiceValidationError(
                    "The selected Control D service target is ambiguous"
                )
            raise ServiceValidationError(
                "The selected Control D service target could not be resolved "
                "for one or more targeted profiles"
            )
        profile_services[profile_pk] = frozenset(resolved_service_ids)

    return profile_services


def _resolve_profile_service_target(
    hass: HomeAssistant,
    call: ServiceCall,
    *,
    allow_entity_ids: bool = True,
    allow_profile_names: bool = False,
    profile_device_field: str = ATTR_DEVICE_ID,
    require_profile_selector: bool = False,
) -> ResolvedProfileServiceTarget:
    """Resolve service inputs into one config entry and one or more profiles."""
    entity_ids = set(_ensure_list(call.data.get(ATTR_ENTITY_ID)))
    device_ids = set(_ensure_list(call.data.get(profile_device_field)))
    explicit_entry_ids = set(_ensure_list(call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID)))
    config_entry_name = call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME)
    requested_profile_names = _ensure_name_list(
        call.data.get(SERVICE_FIELD_PROFILE_NAME)
    )

    if not allow_entity_ids:
        entity_ids.clear()
    if not allow_profile_names:
        requested_profile_names = []

    loaded_entries = {
        entry.entry_id: entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if _entry_runtime(entry) is not None
    }

    entry = _resolve_loaded_entry(
        hass,
        entry_ids=explicit_entry_ids,
        entry_name=(config_entry_name if isinstance(config_entry_name, str) else None),
        loaded_entries=loaded_entries,
        entity_ids=entity_ids,
        device_ids=device_ids,
    )

    targeted_profiles = _resolve_selected_profile_pks(
        hass,
        entry,
        entity_ids=entity_ids,
        device_ids=device_ids,
        requested_profile_names=requested_profile_names,
        loaded_entries=loaded_entries,
    )

    if require_profile_selector and not targeted_profiles:
        raise ServiceValidationError(
            "Select at least one Control D profile by ID or name",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_PROFILE_TARGET_REQUIRED,
        )

    if not targeted_profiles and (
        explicit_entry_ids or config_entry_name or len(loaded_entries) == 1
    ):
        targeted_profiles.update(entry.runtime_data.managers.device.managed_profile_pks)

    if not targeted_profiles:
        raise ServiceValidationError(
            "The selected target did not resolve to any Control D profiles",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
        )

    return ResolvedProfileServiceTarget(
        entry=entry,
        profile_pks=frozenset(targeted_profiles),
    )


def _resolve_loaded_entry(
    hass: HomeAssistant,
    *,
    entry_ids: set[str],
    entry_name: str | None,
    loaded_entries: dict[str, ControlDManagerConfigEntry],
    entity_ids: set[str],
    device_ids: set[str],
) -> ControlDManagerConfigEntry:
    """Resolve the single loaded entry targeted by the service call."""
    if not entry_ids and entry_name is None:
        inferred_entry_ids = set()
        if entity_ids:
            inferred_entry_ids.update(
                _collect_entry_ids_from_entities(hass, entity_ids, loaded_entries)
            )
        if device_ids:
            inferred_entry_ids.update(
                _collect_entry_ids_from_devices(hass, device_ids, loaded_entries)
            )
        entry_ids = inferred_entry_ids

    return _get_loaded_entry(
        hass,
        entry_ids=entry_ids,
        entry_name=entry_name,
        loaded_entries=list(loaded_entries.values()),
    )


def _collect_entry_ids_from_entities(
    hass: HomeAssistant,
    entity_ids: set[str],
    loaded_entries: dict[str, ControlDManagerConfigEntry],
) -> set[str]:
    """Collect loaded config entries referenced by entity targets."""
    entity_registry = er.async_get(hass)
    inferred_entry_ids: set[str] = set()
    for entity_id in entity_ids:
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None:
            raise ServiceValidationError(
                f"Entity {entity_id} is not a Control D target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )
        if entity_entry.config_entry_id in loaded_entries:
            inferred_entry_ids.add(entity_entry.config_entry_id)
            continue

        if entity_entry.config_entry_id is None:
            raise ServiceValidationError(
                f"Entity {entity_id} is not a Control D target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )

        config_entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
        if config_entry is not None and config_entry.domain == DOMAIN:
            raise ServiceValidationError(
                "Config entry is not loaded",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_CONFIG_ENTRY_NOT_LOADED,
            )

        raise ServiceValidationError(
            f"Entity {entity_id} is not a Control D target",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
        )

    return inferred_entry_ids


def _collect_entry_ids_from_devices(
    hass: HomeAssistant,
    device_ids: set[str],
    loaded_entries: dict[str, ControlDManagerConfigEntry],
) -> set[str]:
    """Collect loaded config entries referenced by device targets."""
    device_registry = dr.async_get(hass)
    inferred_entry_ids: set[str] = set()
    for device_id in device_ids:
        device_entry = device_registry.async_get(device_id)
        if device_entry is None:
            raise ServiceValidationError(
                f"Device {device_id} is not a Control D target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )

        matching_loaded_entries = set(device_entry.config_entries) & set(loaded_entries)
        if matching_loaded_entries:
            inferred_entry_ids.update(matching_loaded_entries)
            continue

        if any(
            (config_entry := hass.config_entries.async_get_entry(config_entry_id))
            is not None
            and config_entry.domain == DOMAIN
            for config_entry_id in device_entry.config_entries
        ):
            raise ServiceValidationError(
                "Config entry is not loaded",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_CONFIG_ENTRY_NOT_LOADED,
            )

        raise ServiceValidationError(
            f"Device {device_id} is not a Control D target",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
        )

    return inferred_entry_ids


def _resolve_profiles_from_entity_ids(
    hass: HomeAssistant,
    entry: ControlDManagerConfigEntry,
    entity_ids: set[str],
    *,
    loaded_entries: dict[str, ControlDManagerConfigEntry],
) -> set[str]:
    """Resolve one or more profile identifiers from entity targets."""
    entity_registry = er.async_get(hass)
    targeted_profiles: set[str] = set()

    for entity_id in entity_ids:
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None:
            raise ServiceValidationError(
                f"Entity {entity_id} is not a Control D target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )
        if entity_entry.config_entry_id != entry.entry_id:
            if entity_entry.config_entry_id in loaded_entries:
                raise ServiceValidationError(
                    "Profile targets must belong to the selected Control D "
                    "config entry",
                    translation_domain=DOMAIN,
                    translation_key=TRANS_KEY_PROFILE_TARGET_AMBIGUOUS,
                )
            raise ServiceValidationError(
                f"Entity {entity_id} is not a Control D target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )

        if entity_entry.device_id is not None:
            targeted_profiles.update(
                _resolve_profiles_from_device_ids(
                    hass, entry, {entity_entry.device_id}, loaded_entries=loaded_entries
                )
            )
            continue

        targeted_profiles.update(
            _resolve_profiles_from_unique_id(entry, entity_entry.unique_id)
        )

    return targeted_profiles


def _resolve_profiles_from_device_ids(
    hass: HomeAssistant,
    entry: ControlDManagerConfigEntry,
    device_ids: set[str],
    *,
    loaded_entries: dict[str, ControlDManagerConfigEntry],
) -> set[str]:
    """Resolve one or more profile identifiers from device targets."""
    device_registry = dr.async_get(hass)
    targeted_profiles: set[str] = set()

    for device_id in device_ids:
        device_entry = device_registry.async_get(device_id)
        if device_entry is None:
            raise ServiceValidationError(
                f"Device {device_id} is not a Control D target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )
        if entry.entry_id not in device_entry.config_entries:
            if set(device_entry.config_entries) & set(loaded_entries):
                raise ServiceValidationError(
                    "Profile targets must belong to the selected Control D "
                    "config entry",
                    translation_domain=DOMAIN,
                    translation_key=TRANS_KEY_PROFILE_TARGET_AMBIGUOUS,
                )
            raise ServiceValidationError(
                f"Device {device_id} is not a Control D target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )

        try:
            targeted_profiles.update(
                entry.runtime_data.managers.device.resolve_profile_targets_from_device_ids(
                    {device_id}
                )
            )
        except ValueError as err:
            raise ServiceValidationError(
                str(err),
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            ) from err

    return targeted_profiles


def _resolve_profiles_from_unique_id(
    entry: ControlDManagerConfigEntry, unique_id: str
) -> set[str]:
    """Resolve profile identifiers from a Control D entity unique ID."""
    profile_prefix = f"{entry.runtime_data.instance_id}::profile::"
    if unique_id.startswith(profile_prefix):
        profile_key = unique_id.removeprefix(profile_prefix).split("::", 1)[0]
        return {profile_key}

    instance_prefix = f"{entry.runtime_data.instance_id}::instance::"
    if unique_id.startswith(instance_prefix):
        return set(entry.runtime_data.managers.device.managed_profile_pks)

    raise ServiceValidationError(
        "The selected target did not resolve to any Control D profiles",
        translation_domain=DOMAIN,
        translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
    )


def _get_loaded_entry(
    hass: HomeAssistant,
    *,
    entry_ids: set[str],
    entry_name: str | None,
    loaded_entries: list[ControlDManagerConfigEntry],
) -> ControlDManagerConfigEntry:
    """Return one loaded Control D config entry or raise a validation error."""
    if entry_ids:
        if len(entry_ids) > 1:
            raise ServiceValidationError(
                "Control D service targets must resolve to exactly one "
                "configured instance",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_MULTIPLE_ENTRIES_LOADED,
            )
        entry_id = next(iter(entry_ids))
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise ServiceValidationError(
                "Config entry not found",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_CONFIG_ENTRY_NOT_FOUND,
            )
        if entry.domain != DOMAIN:
            raise ServiceValidationError(
                "Config entry does not belong to Control D Manager",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_WRONG_INTEGRATION_ENTRY,
            )
        if _entry_runtime(entry) is None:
            raise ServiceValidationError(
                "Config entry is not loaded",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_CONFIG_ENTRY_NOT_LOADED,
            )
        return entry

    if entry_name:
        matching_entries = [
            entry for entry in loaded_entries if entry.title == entry_name
        ]
        if not matching_entries:
            raise ServiceValidationError(
                "Config entry name not found",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_CONFIG_ENTRY_NAME_NOT_FOUND,
            )
        if len(matching_entries) > 1:
            raise ServiceValidationError(
                "Config entry name is ambiguous; use config_entry_id",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_CONFIG_ENTRY_NAME_AMBIGUOUS,
            )
        return matching_entries[0]

    if len(loaded_entries) == 1:
        return loaded_entries[0]

    raise ServiceValidationError(
        "Multiple Control D entries are loaded; use config_entry_id, "
        "config_entry_name, profile_id, or profile_name",
        translation_domain=DOMAIN,
        translation_key=TRANS_KEY_MULTIPLE_ENTRIES_LOADED,
    )


def _ensure_list(value: str | list[str] | None) -> list[str]:
    """Normalize a service field into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    if isinstance(value, str) and value:
        return [value]
    return []


def _ensure_name_list(value: str | list[str] | None) -> list[str]:
    """Normalize a name field into a list of non-empty values."""
    if isinstance(value, list):
        return [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _resolve_selected_profile_pks(
    hass: HomeAssistant,
    entry: ControlDManagerConfigEntry,
    *,
    entity_ids: set[str],
    device_ids: set[str],
    requested_profile_names: list[str],
    loaded_entries: dict[str, ControlDManagerConfigEntry],
) -> set[str]:
    """Resolve explicit profile selectors using a stable precedence order.

    Selection precedence is:
    1. `entity_id`
    2. `device_id`
    3. `profile_name`
    """
    if entity_ids:
        return _resolve_profiles_from_entity_ids(
            hass, entry, entity_ids, loaded_entries=loaded_entries
        )
    if device_ids:
        return _resolve_profiles_from_device_ids(
            hass, entry, device_ids, loaded_entries=loaded_entries
        )
    if requested_profile_names:
        return _resolve_profiles_from_names(entry, requested_profile_names)
    return set()


def _resolve_profiles_from_names(
    entry: ControlDManagerConfigEntry,
    requested_profile_names: list[str],
) -> set[str]:
    """Resolve one or more profile identifiers from profile names."""
    managed_profiles = {
        profile_pk: profile
        for profile_pk, profile in entry.runtime_data.registry.profiles.items()
        if profile_pk in entry.runtime_data.managers.device.managed_profile_pks
    }
    targeted_profiles: set[str] = set()

    for requested_name in requested_profile_names:
        normalized_requested_name = _normalize_name(requested_name)
        matches = [
            profile_pk
            for profile_pk, profile in managed_profiles.items()
            if _normalize_name(profile.name) == normalized_requested_name
        ]
        if len(matches) == 1:
            targeted_profiles.add(matches[0])
            continue
        if len(matches) > 1:
            raise ServiceValidationError(
                "The selected Control D profile target is ambiguous",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_AMBIGUOUS,
            )
        raise ServiceValidationError(
            "The selected Control D profile target could not be resolved",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
        )

    return targeted_profiles


def _entry_runtime(entry: ConfigEntry) -> ControlDManagerRuntime | None:
    """Return the attached runtime when the config entry is fully loaded."""
    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, ControlDManagerRuntime):
        return runtime
    return None
