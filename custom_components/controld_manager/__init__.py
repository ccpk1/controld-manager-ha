"""Control D Manager integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import (
    ControlDApiAuthError,
    ControlDAPIClient,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from .const import (
    CONF_API_TOKEN,
    DEFAULT_PAUSE_MINUTES,
    DOMAIN,
    PLATFORMS,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
    SERVICE_FIELD_CONFIG_ENTRY_NAME,
    SERVICE_FIELD_MINUTES,
    SERVICE_PAUSE_PROFILE,
    SERVICE_RESUME_PROFILE,
    TRANS_KEY_CONFIG_ENTRY_NAME_AMBIGUOUS,
    TRANS_KEY_CONFIG_ENTRY_NAME_NOT_FOUND,
    TRANS_KEY_CONFIG_ENTRY_NOT_FOUND,
    TRANS_KEY_CONFIG_ENTRY_NOT_LOADED,
    TRANS_KEY_MULTIPLE_ENTRIES_LOADED,
    TRANS_KEY_PROFILE_TARGET_AMBIGUOUS,
    TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
    TRANS_KEY_WRONG_INTEGRATION_ENTRY,
)
from .coordinator import ControlDManagerDataUpdateCoordinator
from .managers import (
    DeviceManager,
    EndpointManager,
    EntityManager,
    IntegrationManager,
    ProfileManager,
)
from .models import (
    ControlDManagerRuntime,
    ControlDManagerSet,
    ControlDOptions,
    ControlDRefreshIntervals,
    ControlDRegistry,
)

ControlDManagerConfigEntry = ConfigEntry[ControlDManagerRuntime]

PAUSE_PROFILE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): vol.Any(cv.string, [cv.string]),
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
        vol.Optional(
            SERVICE_FIELD_MINUTES, default=DEFAULT_PAUSE_MINUTES
        ): cv.positive_int,
    }
)

RESUME_PROFILE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_ID): vol.Any(cv.string, [cv.string]),
        vol.Optional(SERVICE_FIELD_CONFIG_ENTRY_NAME): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up shared Control D services."""
    del config

    async def async_handle_pause_profile(call: ServiceCall) -> None:
        """Pause targeted profiles for the requested duration."""
        entry, profile_pks = _resolve_profile_service_targets(hass, call)
        try:
            await entry.runtime_data.managers.profile.async_pause_profiles(
                profile_pks, call.data[SERVICE_FIELD_MINUTES]
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError(
                "Unable to pause the targeted Control D profiles"
            ) from err

    async def async_handle_resume_profile(call: ServiceCall) -> None:
        """Resume targeted profiles immediately."""
        entry, profile_pks = _resolve_profile_service_targets(hass, call)
        try:
            await entry.runtime_data.managers.profile.async_resume_profiles(profile_pks)
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
        ) as err:
            raise HomeAssistantError(
                "Unable to resume the targeted Control D profiles"
            ) from err

    if not hass.services.has_service(DOMAIN, SERVICE_PAUSE_PROFILE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PAUSE_PROFILE,
            async_handle_pause_profile,
            schema=PAUSE_PROFILE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESUME_PROFILE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESUME_PROFILE,
            async_handle_resume_profile,
            schema=RESUME_PROFILE_SERVICE_SCHEMA,
        )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ControlDManagerConfigEntry
) -> bool:
    """Set up Control D Manager from a config entry."""
    session = async_get_clientsession(hass)
    client = ControlDAPIClient(entry.data[CONF_API_TOKEN], session)
    options = ControlDOptions.from_mapping(dict(entry.options))

    profile_manager = ProfileManager()
    endpoint_manager = EndpointManager()
    device_manager = DeviceManager()
    entity_manager = EntityManager()
    integration_manager = IntegrationManager(
        profile_manager=profile_manager,
        endpoint_manager=endpoint_manager,
        device_manager=device_manager,
        entity_manager=entity_manager,
    )
    managers = ControlDManagerSet(
        integration=integration_manager,
        device=device_manager,
        entity=entity_manager,
        profile=profile_manager,
        endpoint=endpoint_manager,
    )
    runtime = ControlDManagerRuntime(
        entry_id=entry.entry_id,
        instance_id=str(entry.unique_id),
        client=client,
        options=options,
        refresh_intervals=ControlDRefreshIntervals(
            configuration_sync=options.configuration_sync_interval,
            profile_analytics=options.profile_analytics_interval,
            endpoint_analytics=options.endpoint_analytics_interval,
        ),
        registry=ControlDRegistry.empty(),
        managers=managers,
    )
    managers.attach_runtime(runtime)

    coordinator = ControlDManagerDataUpdateCoordinator(hass, entry, runtime)
    runtime.coordinator = coordinator

    try:
        await coordinator.async_config_entry_first_refresh()
    except ControlDApiAuthError as err:
        raise ConfigEntryAuthFailed("Control D authentication failed") from err
    except (ControlDApiConnectionError, ControlDApiResponseError) as err:
        raise ConfigEntryNotReady("Unable to initialize Control D runtime") from err

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ControlDManagerConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _resolve_profile_service_targets(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[ControlDManagerConfigEntry, set[str]]:
    """Resolve service targets into one config entry and a set of profile PKs."""
    entity_ids = set(_ensure_list(call.data.get(ATTR_ENTITY_ID)))
    config_entry_ids = set(_ensure_list(call.data.get(SERVICE_FIELD_CONFIG_ENTRY_ID)))
    config_entry_name = call.data.get(SERVICE_FIELD_CONFIG_ENTRY_NAME)

    loaded_entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if isinstance(entry.runtime_data, ControlDManagerRuntime)
    ]

    entry = _get_loaded_entry(
        hass,
        entry_ids=config_entry_ids,
        entry_name=(config_entry_name if isinstance(config_entry_name, str) else None),
        loaded_entries=loaded_entries,
    )

    entity_registry = er.async_get(hass)
    targeted_profiles: set[str] = set()

    for entity_id in entity_ids:
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None or entity_entry.platform != DOMAIN:
            raise ServiceValidationError(
                f"Entity {entity_id} is not a Control D profile target",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )
        if entity_entry.domain != "switch" or not entity_entry.unique_id.endswith(
            "::paused"
        ):
            raise ServiceValidationError(
                f"Entity {entity_id} is not a Control D profile selector",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
            )
        if entity_entry.config_entry_id != entry.entry_id:
            raise ServiceValidationError(
                "Profile targets must belong to the selected Control D config entry",
                translation_domain=DOMAIN,
                translation_key=TRANS_KEY_PROFILE_TARGET_AMBIGUOUS,
            )
        profile_pk = entity_entry.unique_id.removeprefix(
            f"{entry.runtime_data.instance_id}::profile::"
        )
        profile_pk = profile_pk.removesuffix("::paused")
        targeted_profiles.add(profile_pk)

    if not targeted_profiles and (
        config_entry_ids or config_entry_name or len(loaded_entries) == 1
    ):
        targeted_profiles.update(entry.runtime_data.managers.device.managed_profile_pks)

    if not targeted_profiles:
        raise ServiceValidationError(
            "The selected target did not resolve to any Control D profiles",
            translation_domain=DOMAIN,
            translation_key=TRANS_KEY_PROFILE_TARGET_NOT_FOUND,
        )

    return entry, targeted_profiles


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
        if not isinstance(entry.runtime_data, ControlDManagerRuntime):
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
        "Multiple Control D entries are loaded; use config_entry_id or "
        "config_entry_name",
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
