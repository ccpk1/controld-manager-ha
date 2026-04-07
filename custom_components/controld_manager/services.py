"""Shared Home Assistant services for Control D Manager."""

from __future__ import annotations

from dataclasses import dataclass

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

from .api import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from .const import (
    DEFAULT_DISABLE_MINUTES,
    DOMAIN,
    SERVICE_DISABLE_PROFILE,
    SERVICE_ENABLE_PROFILE,
    SERVICE_FIELD_CATALOG_TYPE,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_FIELD_ENABLED,
    SERVICE_FIELD_FILTER_ID,
    SERVICE_FIELD_FILTER_NAME,
    SERVICE_FIELD_MINUTES,
    SERVICE_FIELD_PROFILE_ID,
    SERVICE_FIELD_PROFILE_NAME,
    SERVICE_GET_CATALOG,
    SERVICE_SET_FILTER_STATE,
    TRANS_KEY_CONFIG_ENTRY_NAME_AMBIGUOUS,
    TRANS_KEY_CONFIG_ENTRY_NAME_NOT_FOUND,
    TRANS_KEY_CONFIG_ENTRY_NOT_FOUND,
    TRANS_KEY_CONFIG_ENTRY_NOT_LOADED,
    TRANS_KEY_MULTIPLE_ENTRIES_LOADED,
    TRANS_KEY_PROFILE_TARGET_AMBIGUOUS,
    TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
    TRANS_KEY_PROFILE_TARGET_REQUIRED,
    TRANS_KEY_WRONG_INTEGRATION_ENTRY,
)
from .models import ControlDManagerRuntime
from .service_selectors import _normalize_name, _resolve_selected_filter_pks

ControlDManagerConfigEntry = ConfigEntry[ControlDManagerRuntime]

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
            await (
                resolved_target.entry.runtime_data.managers.profile.async_disable_profiles(
                    set(resolved_target.profile_pks),
                    call.data[SERVICE_FIELD_MINUTES],
                )
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError(
                "Unable to disable the targeted Control D profiles"
            ) from err

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
            await (
                resolved_target.entry.runtime_data.managers.profile.async_enable_profiles(
                    set(resolved_target.profile_pks)
                )
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError(
                "Unable to enable the targeted Control D profiles"
            ) from err

    async def async_handle_set_filter_state(call: ServiceCall) -> None:
        """Enable or disable one named filter across targeted profiles."""
        resolved_target = _resolve_filter_service_target(hass, call)
        try:
            await (
                resolved_target.entry.runtime_data.managers.profile.async_set_filters_enabled(
                    resolved_target.profile_filters,
                    call.data[SERVICE_FIELD_ENABLED],
                )
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError(
                "Unable to update the targeted Control D filters"
            ) from err

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
