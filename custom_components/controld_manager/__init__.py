"""Control D Manager integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
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
    PLATFORMS,
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
from .services import async_register_services

ControlDManagerConfigEntry = ConfigEntry[ControlDManagerRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up shared Control D services."""
    del config
    await async_register_services(hass)
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
