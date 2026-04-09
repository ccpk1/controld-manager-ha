"""Runtime and manager tests for Control D Manager."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, call, patch

import pytest
from aiohttp import ClientSession
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.api.client import ControlDAPIClient
from custom_components.controld_manager.api.exceptions import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
)
from custom_components.controld_manager.config_flow import ControlDManagerOptionsFlow
from custom_components.controld_manager.const import CONF_API_TOKEN, DOMAIN
from custom_components.controld_manager.managers import (
    DeviceManager,
    EndpointManager,
    EntityManager,
    IntegrationManager,
    ProfileManager,
)
from custom_components.controld_manager.models import (
    ControlDAccountAnalytics,
    ControlDInventoryPayload,
    ControlDOptions,
    ControlDProfileDetailPayload,
    ControlDRegistry,
)

OPTION_CATALOG = (
    {
        "PK": "ai_malware",
        "title": "AI Malware Filter",
        "description": "Blocks malicious domains using machine learning.",
        "type": "dropdown",
        "default_value": {"0.9": "Minimal", "0.7": "Standard", "0.5": "Aggressive"},
        "info_url": "https://docs.controld.com/docs/ai-malware-filter",
    },
    {
        "PK": "safesearch",
        "title": "Safe Search",
        "description": "Prevent search engines from showing mature content.",
        "type": "toggle",
        "default_value": 0,
        "info_url": "https://docs.controld.com/docs/safe-search",
    },
    {
        "PK": "b_resp",
        "title": "Block Response",
        "description": "Choose how to respond to blocked queries.",
        "type": "dropdown",
        "default_value": {
            "0": "0.0.0.0 / ::",
            "3": "NXDOMAIN",
            "5": "REFUSED",
        },
        "info_url": "https://docs.controld.com/docs/blocked-query-response",
    },
    {
        "PK": "ttl_blck",
        "title": "Block TTL",
        "description": "DNS record TTL (in seconds) when blocking.",
        "type": "field",
        "default_value": 10,
        "info_url": "https://docs.controld.com/docs/ttl-overrides",
    },
    {
        "PK": "ttl_spff",
        "title": "Redirect TTL",
        "description": "DNS record TTL (in seconds) when redirecting.",
        "type": "field",
        "default_value": 20,
        "info_url": "https://docs.controld.com/docs/ttl-overrides",
    },
    {
        "PK": "ttl_pass",
        "title": "Bypass TTL",
        "description": "DNS record TTL (in seconds) when bypassing.",
        "type": "field",
        "default_value": 300,
        "info_url": "https://docs.controld.com/docs/ttl-overrides",
    },
    {
        "PK": "ecs_subnet",
        "title": "EDNS Client Subnet",
        "description": "Override the EDNS Client Subnet for this profile.",
        "type": "dropdown",
        "default_value": ["No ECS", "Auto", "Custom"],
        "info_url": "https://docs.controld.com/docs/ecs-custom-subnet",
    },
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


def _sample_account_analytics() -> ControlDAccountAnalytics:
    """Return representative account analytics for runtime tests."""
    return ControlDAccountAnalytics(
        total_queries=82268,
        blocked_queries=9950,
        bypassed_queries=72318,
        redirected_queries=0,
        blocked_queries_ratio=12.094617591287014,
        start_time=datetime(2026, 4, 7, tzinfo=UTC),
        end_time=datetime(2026, 4, 8, tzinfo=UTC),
    )


def _sample_profile_analytics(profile_pk: str) -> ControlDAccountAnalytics:
    """Return representative profile analytics for runtime tests."""
    if profile_pk == "profile-1":
        return ControlDAccountAnalytics(
            total_queries=78033,
            blocked_queries=9678,
            bypassed_queries=68355,
            redirected_queries=0,
            blocked_queries_ratio=12.402957209903248,
            start_time=datetime(2026, 4, 7, tzinfo=UTC),
            end_time=datetime(2026, 4, 8, tzinfo=UTC),
        )

    return ControlDAccountAnalytics(
        total_queries=1235,
        blocked_queries=120,
        bypassed_queries=1110,
        redirected_queries=5,
        blocked_queries_ratio=9.716599190283401,
        start_time=datetime(2026, 4, 7, tzinfo=UTC),
        end_time=datetime(2026, 4, 8, tzinfo=UTC),
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
    assert registry.endpoints["router-1"].associated_client_count == 1
    assert registry.endpoints["device-1"].associated_client_count == 0
    assert registry.endpoints["device-1"].parent_device_id == "router-1"
    assert registry.endpoint_inventory.discovered_endpoint_count == 2
    assert registry.endpoint_inventory.router_client_count == 1
    assert registry.endpoint_inventory.protected_endpoint_count == 3


def test_integration_manager_reads_org_stats_endpoint_fallback() -> None:
    """Nested organization stats-endpoint metadata should be preserved."""
    device_manager = DeviceManager()
    entity_manager = EntityManager()
    integration_manager = IntegrationManager(
        profile_manager=ProfileManager(),
        endpoint_manager=EndpointManager(),
        device_manager=device_manager,
        entity_manager=entity_manager,
    )

    inventory = _sample_inventory()
    inventory = ControlDInventoryPayload(
        user={
            "id": "user-123",
            "PK": "account-pk",
            "org": {"stats_endpoint": "us-east1-org01"},
            "safe_countries": ["US", "CA"],
        },
        profiles=inventory.profiles,
        devices=inventory.devices,
    )

    with (
        patch.object(device_manager, "sync_registry"),
        patch.object(entity_manager, "sync_registry"),
    ):
        integration_manager.attach_runtime(
            cast(Any, SimpleNamespace(options=ControlDOptions()))
        )
        registry = integration_manager.build_registry(inventory)

    assert registry.user is not None
    assert registry.user.stats_endpoint == "us-east1-org01"


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
                options=(
                    {"PK": "safesearch", "value": 1},
                    {"PK": "ai_malware", "value": 0.9},
                    {"PK": "ecs_subnet", "value": 1},
                    {"PK": "ttl_blck", "value": 11},
                ),
                default_rule={"do": 1, "status": 1},
            )
        },
        option_catalog=OPTION_CATALOG,
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
    default_rule_row = registry.default_rules_by_profile["profile-1"]
    option_row = registry.options_by_profile["profile-1"]["ai_malware"]
    block_response_row = registry.options_by_profile["profile-1"]["b_resp"]
    ecs_row = registry.options_by_profile["profile-1"]["ecs_subnet"]
    toggle_row = registry.options_by_profile["profile-1"]["safesearch"]
    ttl_row = registry.options_by_profile["profile-1"]["ttl_blck"]
    assert filter_row.effective_level_slug == "porn"
    assert filter_row.effective_level_title == "Relaxed"
    assert service_row.current_mode == "blocked"
    assert default_rule_row.current_mode == "bypassing"
    assert option_row.current_select_option == "Minimal"
    assert block_response_row.select_options == (
        "Off",
        "0.0.0.0 / ::",
        "NXDOMAIN",
        "REFUSED",
    )
    assert ecs_row.entity_kind == "select"
    assert ecs_row.select_options == ("Off", "No ECS", "Auto")
    assert toggle_row.is_enabled is True
    assert ttl_row.entity_kind == "toggle"
    assert ttl_row.default_value_key == "10"
    assert ttl_row.is_enabled is True


async def test_profile_option_write_payload_matches_browser_contract() -> None:
    """Profile option writes should match the browser-verified option contract."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_set_profile_option(
                "profile-1",
                "ai_malware",
                enabled=True,
                value="0.7",
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/options/ai_malware",
        {"status": 1, "value": "0.7"},
    )


async def test_profile_default_rule_write_payload_matches_browser_contract() -> None:
    """Default-rule writes should match the browser-verified contract."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_set_profile_default_rule(
                "profile-1",
                action_do=3,
                via="LOCAL",
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/default",
        {"do": 3, "status": 1, "via": "LOCAL"},
    )


async def test_profile_group_write_payload_matches_browser_contract() -> None:
    """Folder-rule writes should match the browser-verified group contract."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_set_profile_group(
                "profile-1",
                "3",
                name="test folder - single allow rule",
                enabled=True,
                action_do=1,
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/groups/3",
        {
            "name": "test folder - single allow rule",
            "status": 1,
            "do": 1,
            "via": "-1",
            "via_v6": "-1",
        },
    )


async def test_profile_group_off_write_payload_matches_browser_contract() -> None:
    """Folder-rule off writes should preserve enabled status and send do=-1."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_set_profile_group(
                "profile-1",
                "1",
                name="test folder",
                enabled=True,
                action_do=-1,
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/groups/1",
        {
            "name": "test folder",
            "status": 1,
            "do": -1,
            "via": "-1",
            "via_v6": "-1",
        },
    )


async def test_ttl_option_toggle_restore_uses_catalog_default() -> None:
    """TTL toggles should restore the catalog default value when re-enabled."""

    def _consume_task(coro: Any) -> None:
        coro.close()

    profile_manager = ProfileManager()
    runtime = cast(
        Any,
        SimpleNamespace(
            client=SimpleNamespace(async_set_profile_option=AsyncMock()),
            registry=SimpleNamespace(
                options_by_profile={
                    "profile-1": {
                        "ttl_blck": IntegrationManager._normalize_profile_options(
                            OPTION_CATALOG,
                            ({"PK": "ttl_blck", "value": 11},),
                        )["ttl_blck"]
                    }
                }
            ),
            active_coordinator=SimpleNamespace(
                async_update_listeners=lambda: None,
                hass=SimpleNamespace(async_create_task=_consume_task),
                async_refresh=AsyncMock(),
            ),
        ),
    )
    profile_manager.attach_runtime(runtime)

    await profile_manager.async_set_profile_option_toggle("profile-1", "ttl_blck", True)

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ttl_blck",
        enabled=True,
        value="10",
    )


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


async def test_rule_rich_write_payload_matches_browser_contract() -> None:
    """Rich rule writes should match the browser-verified rule API contract."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_update_profile_rule_rich(
                "profile-1",
                "example.com",
                enabled=False,
                action_do=0,
                group_pk=None,
                ttl=1775563200,
                comment="new rule comment",
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/rules",
        {
            "do": 0,
            "status": 0,
            "via": "-1",
            "via_v6": "-1",
            "ttl": 1775563200,
            "hostnames": ["example.com"],
            "group": 0,
            "comment": "new rule comment",
        },
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
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_account_analytics",
            new=AsyncMock(return_value=_sample_account_analytics()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_analytics",
            new=AsyncMock(
                side_effect=lambda _endpoint, profile_pk, **_kwargs: (
                    _sample_profile_analytics(profile_pk)
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(return_value=ControlDProfileDetailPayload()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=[]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime is not None
    assert runtime.instance_id == "user-123"
    assert runtime.registry.user is not None
    assert runtime.registry.user.account_pk == "account-pk"
    assert runtime.registry.account_analytics is not None
    assert runtime.registry.account_analytics.total_queries == 82268
    assert runtime.registry.account_analytics.blocked_queries == 9950
    assert runtime.registry.account_analytics.bypassed_queries == 72318
    assert runtime.registry.account_analytics.redirected_queries == 0
    assert (
        runtime.registry.profile_analytics_by_profile["profile-1"].total_queries
        == 78033
    )
    assert (
        runtime.registry.profile_analytics_by_profile["profile-2"].redirected_queries
        == 5
    )
    assert runtime.managers.integration.runtime is runtime
    assert runtime.managers.profile.runtime is runtime
    assert runtime.coordinator is not None
    assert runtime.sync_status.last_successful_refresh is not None
    assert runtime.sync_status.last_refresh_error is None
    assert runtime.sync_status.consecutive_failed_refreshes == 0


async def test_coordinator_refresh_raises_auth_failed_for_reauth(hass) -> None:
    """Auth failures during refresh should trigger Home Assistant reauth."""
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
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_account_analytics",
            new=AsyncMock(return_value=_sample_account_analytics()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_analytics",
            new=AsyncMock(
                side_effect=lambda _endpoint, profile_pk, **_kwargs: (
                    _sample_profile_analytics(profile_pk)
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(return_value=ControlDProfileDetailPayload()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=[]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime = entry.runtime_data
    with (
        patch.object(
            runtime.client,
            "async_get_inventory",
            new=AsyncMock(side_effect=ControlDApiAuthError("bad token")),
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await runtime.active_coordinator._async_update_data()


async def test_coordinator_requests_last_day_analytics_window(hass) -> None:
    """Account and profile analytics should use the rolling last-day window."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value"},
        unique_id="user-123",
    )
    entry.add_to_hass(hass)

    analytics_mock = AsyncMock(return_value=_sample_account_analytics())
    profile_analytics_mock = AsyncMock(
        side_effect=lambda _endpoint, profile_pk, **_kwargs: _sample_profile_analytics(
            profile_pk
        )
    )

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=_sample_inventory()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_account_analytics",
            new=analytics_mock,
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_analytics",
            new=profile_analytics_mock,
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(return_value=ControlDProfileDetailPayload()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.coordinator.dt_util.now",
            return_value=datetime(2026, 4, 8, 13, 0, 0, tzinfo=UTC),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    analytics_mock.assert_awaited_once_with(
        "america",
        start_time=datetime(2026, 4, 7, 13, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 8, 13, 0, 0, tzinfo=UTC),
    )
    profile_analytics_mock.assert_has_awaits(
        [
            call(
                "america",
                "profile-1",
                start_time=datetime(2026, 4, 7, 13, 0, 0, tzinfo=UTC),
                end_time=datetime(2026, 4, 8, 13, 0, 0, tzinfo=UTC),
            ),
            call(
                "america",
                "profile-2",
                start_time=datetime(2026, 4, 7, 13, 0, 0, tzinfo=UTC),
                end_time=datetime(2026, 4, 8, 13, 0, 0, tzinfo=UTC),
            ),
        ]
    )


async def test_coordinator_logs_unavailable_once_and_recovery(hass, caplog) -> None:
    """Connection failures should log once, then log recovery on success."""
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
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_account_analytics",
            new=AsyncMock(return_value=_sample_account_analytics()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_analytics",
            new=AsyncMock(
                side_effect=lambda _endpoint, profile_pk, **_kwargs: (
                    _sample_profile_analytics(profile_pk)
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(return_value=ControlDProfileDetailPayload()),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=[]),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime = entry.runtime_data
    caplog.set_level(logging.INFO)
    with (
        patch.object(
            runtime.client,
            "async_get_inventory",
            new=AsyncMock(
                side_effect=[
                    ControlDApiConnectionError("offline-1"),
                    ControlDApiConnectionError("offline-2"),
                    _sample_inventory(),
                ]
            ),
        ),
        patch.object(
            runtime.client,
            "async_get_profile_detail",
            new=AsyncMock(return_value=ControlDProfileDetailPayload()),
        ),
        patch.object(
            runtime.client,
            "async_get_profile_option_catalog",
            new=AsyncMock(return_value=[]),
        ),
    ):
        for _ in range(2):
            with pytest.raises(UpdateFailed):
                await runtime.active_coordinator._async_update_data()
        await runtime.active_coordinator._async_update_data()

    unavailable_logs = [
        record.message
        for record in caplog.records
        if "API is unavailable" in record.message
    ]
    recovery_logs = [
        record.message
        for record in caplog.records
        if "API is back online" in record.message
    ]
    assert len(unavailable_logs) == 1
    assert len(recovery_logs) == 1


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
            new=AsyncMock(
                return_value=[
                    {"PK": 1, "group": "Allow folder", "action": {"do": 1}},
                    {"PK": 2, "group": "Block folder", "action": {"do": 0}},
                ]
            ),
        ),
        patch(
            "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_profile_rules",
            new=AsyncMock(
                return_value=[
                    {"PK": "example.com", "group": 0, "action": {"do": 0}},
                    {"PK": "example2.com", "group": 1, "action": {"do": 1}},
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
                "expose_external_filters": True,
                "advanced_profile_options": True,
                "endpoint_sensors_enabled": True,
                "endpoint_inactivity_threshold_minutes": 20,
                "allowed_service_categories": ["audio"],
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
            },
        )

    assert result["type"] == "menu"
    assert entry.options["configuration_sync_interval_minutes"] == 20
    assert entry.options["profile_analytics_interval_minutes"] == 5
    assert entry.options["endpoint_analytics_interval_minutes"] == 5
    assert entry.options["profile_policies"]["profile-1"] == {
        "managed_in_home_assistant": True,
        "expose_external_filters": True,
        "advanced_profile_options": True,
        "endpoint_sensors_enabled": True,
        "endpoint_inactivity_threshold_minutes": 20,
        "allowed_service_categories": ["audio"],
        "auto_enable_service_switches": False,
        "exposed_custom_rules": ["group:1", "rule:root|example.com"],
    }

    assert entry.options["profile_policies"].get("profile-2") is None


async def test_options_flow_rule_choice_labels_include_scope_and_action(hass) -> None:
    """Rule selectors should show folder context and action labels."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    flow = ControlDManagerOptionsFlow(entry)
    flow.hass = hass

    with (
        patch(
            "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_profile_groups",
            new=AsyncMock(
                return_value=[
                    {"PK": 1, "group": "Allow folder", "action": {"do": 1}},
                    {"PK": 2, "group": "Block folder", "action": {"do": 0}},
                ]
            ),
        ),
        patch(
            "custom_components.controld_manager.config_flow.ControlDAPIClient.async_get_profile_rules",
            new=AsyncMock(
                return_value=[
                    {"PK": "example.com", "group": 0, "action": {"do": 0}},
                    {"PK": "example2.com", "group": 1, "action": {"do": 1}},
                ]
            ),
        ),
    ):
        choices = await flow._async_get_rule_target_choices("profile-1")

    assert choices["group:1"] == "📁 Allow folder (Bypass)"
    assert choices["group:2"] == "📁 Block folder (Block)"
    assert choices["rule:root|example.com"] == "⛔ example.com (Block)"
    assert (
        choices["rule:group:1|example2.com"]
        == "📁 Allow folder / ↳ ✅ example2.com (Bypass)"
    )


async def test_entity_manager_skips_remove_for_unattached_entity(hass) -> None:
    """Dynamic removal should tolerate entities that have not been added yet."""
    entity_manager = EntityManager()
    entity_manager.attach_runtime(
        cast(
            Any,
            SimpleNamespace(
                active_coordinator=SimpleNamespace(hass=hass),
                entry_id="test-entry-id",
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
