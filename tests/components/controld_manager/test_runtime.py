"""Runtime and manager tests for Control D Manager."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.api.client import ControlDAPIClient
from custom_components.controld_manager.const import CONF_API_TOKEN, DOMAIN
from custom_components.controld_manager.managers import (
    DeviceManager,
    EndpointManager,
    EntityManager,
    IntegrationManager,
    ProfileManager,
)
from custom_components.controld_manager.models import (
    ControlDInventoryPayload,
    ControlDOptions,
    ControlDProfileDetailPayload,
    ControlDRegistry,
)


def _sample_inventory() -> ControlDInventoryPayload:
    """Return a representative inventory payload for runtime tests."""
    return ControlDInventoryPayload(
        user={
            "id": "user-123",
            "PK": "account-pk",
            "stats_endpoint": "america",
            "safe_countries": ["US", "CA"],
        },
        profiles=(
            {"PK": "profile-1", "name": "Primary", "disable_ttl": 1775067384},
            {"PK": "profile-2", "name": "Secondary", "disable": None},
        ),
        devices=(
            {
                "device_id": "router-1",
                "PK": "endpoint-pk-router-1",
                "name": "Firewalla",
                "last_activity": 1775067385,
                "profile": {"PK": "profile-1", "name": "Primary"},
                "clients": {
                    "client-visible": {"alias": "Chads-Phone"},
                    "client-hidden": {"alias": "Office-TV"},
                },
            },
            {
                "device_id": "device-1",
                "PK": "endpoint-pk-1",
                "name": "Chads-Phone",
                "last_activity": 1775067384,
                "profile": {"PK": "profile-1", "name": "Primary"},
                "profile2": {"PK": "profile-2", "name": "Secondary"},
                "parent_device": {"device_id": "router-1"},
            },
        ),
    )


def test_integration_manager_builds_normalized_registry() -> None:
    """Registry shaping should be manager-owned and follow the approved rules."""
    device_manager = DeviceManager()
    entity_manager = EntityManager()
    integration_manager = IntegrationManager(
        profile_manager=ProfileManager(),
        endpoint_manager=EndpointManager(),
        device_manager=device_manager,
        entity_manager=entity_manager,
    )

    with (
        patch.object(device_manager, "sync_registry"),
        patch.object(entity_manager, "sync_registry"),
    ):
        integration_manager.attach_runtime(
            cast(Any, SimpleNamespace(options=ControlDOptions()))
        )
        registry = integration_manager.build_registry(_sample_inventory())

    assert registry.user is not None
    assert registry.user.instance_id == "user-123"
    assert registry.profiles["profile-1"].paused_until == datetime.fromtimestamp(
        1775067384, UTC
    )
    assert registry.endpoints["device-1"].owning_profile_pk == "profile-1"
    assert registry.endpoints["device-1"].attached_profiles[1].profile_pk == "profile-2"
    assert registry.endpoints["device-1"].last_active == datetime.fromtimestamp(
        1775067384, UTC
    )
    assert registry.endpoints["device-1"].parent_device_id == "router-1"
    assert registry.endpoint_inventory.discovered_endpoint_count == 2
    assert registry.endpoint_inventory.router_client_count == 1
    assert registry.endpoint_inventory.protected_endpoint_count == 3


def test_integration_manager_preserves_filter_fallback_and_service_modes() -> None:
    """Disabled modal filters and block services should normalize predictably."""
    device_manager = DeviceManager()
    entity_manager = EntityManager()
    integration_manager = IntegrationManager(
        profile_manager=ProfileManager(),
        endpoint_manager=EndpointManager(),
        device_manager=device_manager,
        entity_manager=entity_manager,
    )

    inventory = ControlDInventoryPayload(
        user=_sample_inventory().user,
        profiles=_sample_inventory().profiles,
        devices=_sample_inventory().devices,
        profile_details={
            "profile-1": ControlDProfileDetailPayload(
                filters=(
                    {
                        "PK": "porn",
                        "name": "Adult Content",
                        "levels": [
                            {"title": "Relaxed", "name": "porn", "status": 0},
                            {
                                "title": "Strict",
                                "name": "porn_strict",
                                "status": 0,
                            },
                        ],
                        "action": None,
                        "status": 0,
                    },
                ),
                services=(
                    {
                        "PK": "truthsocial",
                        "name": "Truth Social",
                        "category": "social",
                        "action": {"do": 0, "status": 1},
                    },
                ),
            )
        },
        service_categories=({"PK": "social", "name": "Social", "count": 1},),
        service_catalog=(
            {"PK": "truthsocial", "name": "Truth Social", "category": "social"},
        ),
    )

    with (
        patch.object(device_manager, "sync_registry"),
        patch.object(entity_manager, "sync_registry"),
    ):
        integration_manager.attach_runtime(
            cast(
                Any,
                SimpleNamespace(
                    options=ControlDOptions.from_mapping(
                        {
                            "profile_policies": {
                                "profile-1": {"allowed_service_categories": ["social"]}
                            }
                        }
                    )
                ),
            )
        )
        registry = integration_manager.build_registry(inventory)

    filter_row = registry.filters_by_profile["profile-1"]["porn"]
    service_row = registry.services_by_profile["profile-1"]["truthsocial"]
    assert filter_row.effective_level_slug == "porn"
    assert filter_row.effective_level_title == "Relaxed"
    assert service_row.current_mode == "Blocked"


async def test_filter_write_payload_matches_browser_contract() -> None:
    """Filter writes should match the browser-verified filter API contract."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_set_profile_filter(
                "profile-1",
                "ads",
                enabled=True,
                action_do=0,
                level_slug="ads_medium",
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/filters/filter/ads",
        {"status": 1, "do": 0, "lvl": "ads_medium"},
    )


async def test_setup_entry_creates_entry_scoped_runtime(hass) -> None:
    """Setting up one entry should create one runtime with attached managers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value"},
        unique_id="user-123",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=_sample_inventory()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(return_value=ControlDProfileDetailPayload()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime is not None
    assert runtime.instance_id == "user-123"
    assert runtime.registry.user is not None
    assert runtime.registry.user.account_pk == "account-pk"
    assert runtime.managers.integration.runtime is runtime
    assert runtime.managers.profile.runtime is runtime
    assert runtime.coordinator is not None
    assert runtime.sync_status.last_successful_refresh is not None
    assert runtime.sync_status.last_refresh_error is None
    assert runtime.sync_status.consecutive_failed_refreshes == 0


async def test_options_flow_saves_typed_profile_policy(hass) -> None:
    """The options flow should persist compact per-profile policy settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_profiles",
            new=AsyncMock(
                return_value=[
                    {"PK": "profile-1", "name": "Primary"},
                    {"PK": "profile-2", "name": "Secondary"},
                ]
            ),
        ),
        patch(
            "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[{"PK": "audio", "name": "Audio"}]),
        ),
        patch(
            "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_profile_groups",
            new=AsyncMock(return_value=[{"PK": 1, "group": "Allow folder"}]),
        ),
        patch(
            "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_profile_rules",
            new=AsyncMock(
                return_value=[
                    {"PK": "example.com", "group": 0},
                    {"PK": "example2.com", "group": 1},
                ]
            ),
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        flow_id = result["flow_id"]
        assert result["type"] == "menu"

        result = await hass.config_entries.options.async_configure(
            flow_id, {"next_step_id": "select_profile"}
        )
        assert result["type"] == "form"

        result = await hass.config_entries.options.async_configure(
            flow_id, {"profile_pk": "profile-1"}
        )
        assert result["type"] == "form"

        result = await hass.config_entries.options.async_configure(
            flow_id,
            {
                "managed_in_home_assistant": True,
                "endpoint_sensors_enabled": True,
                "endpoint_inactivity_threshold_minutes": 20,
                "allowed_service_categories": ["audio"],
                "auto_enable_service_switches": True,
                "exposed_custom_rules": ["group:1", "rule:root|example.com"],
            },
        )
        assert result["type"] == "menu"

        result = await hass.config_entries.options.async_configure(
            flow_id, {"next_step_id": "integration_settings"}
        )
        assert result["type"] == "form"

        result = await hass.config_entries.options.async_configure(
            flow_id,
            {
                "configuration_sync_interval_minutes": 20,
                "profile_analytics_interval_minutes": 6,
                "endpoint_analytics_interval_minutes": 7,
            },
        )

    assert result["type"] == "menu"
    assert entry.options["configuration_sync_interval_minutes"] == 20
    assert entry.options["profile_analytics_interval_minutes"] == 6
    assert entry.options["endpoint_analytics_interval_minutes"] == 7
    assert entry.options["profile_policies"]["profile-1"] == {
        "managed_in_home_assistant": True,
        "endpoint_sensors_enabled": True,
        "endpoint_inactivity_threshold_minutes": 20,
        "allowed_service_categories": ["audio"],
        "auto_enable_service_switches": True,
        "exposed_custom_rules": ["group:1", "rule:root|example.com"],
    }

    assert entry.options["profile_policies"].get("profile-2") is None


async def test_entity_manager_skips_remove_for_unattached_entity() -> None:
    """Dynamic removal should tolerate entities that have not been added yet."""
    entity_manager = EntityManager()
    entity_manager.attach_runtime(
        cast(
            Any,
            SimpleNamespace(
                options=ControlDOptions(),
                registry=ControlDRegistry.empty(),
            ),
        )
    )
    entity_manager.register_platform("switch", lambda entities: None, lambda key: None)

    unattached_entity = SimpleNamespace(hass=None, async_remove=AsyncMock())
    entity_manager._registered_platforms["switch"].live_entities = {
        "profile::profile-1::paused": unattached_entity
    }

    await entity_manager.async_sync_platform("switch")

    unattached_entity.async_remove.assert_not_awaited()
    assert entity_manager._registered_platforms["switch"].live_entities == {}
