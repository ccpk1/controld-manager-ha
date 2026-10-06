"""Runtime and manager tests for Control D Manager."""

# pylint: disable=protected-access,too-many-lines

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
from custom_components.controld_manager.config_flow import (
    FIELD_EXPOSE_ALL_ACTIVE_SERVICES,
    FIELD_EXPOSE_ALL_CUSTOM_RULES,
    ControlDManagerOptionsFlow,
)
from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    DOMAIN,
    SERVICE_EXPOSURE_MANUAL,
    SERVICE_SELECTOR_AUTOMATIC,
)
from custom_components.controld_manager.managers import (
    DeviceManager,
    EndpointManager,
    EntityManager,
    IntegrationManager,
    ProfileManager,
)
from custom_components.controld_manager.models import (
    ControlDAccountAnalytics,
    ControlDAttachedProfile,
    ControlDClientAliasTarget,
    ControlDEndpointSummary,
    ControlDInventoryPayload,
    ControlDOptions,
    ControlDProfileDetailPayload,
    ControlDProfilePolicy,
    ControlDRegistry,
    build_client_alias_target_key,
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


def _client_alias_inventory() -> ControlDInventoryPayload:
    """Return inventory with one explicit client alias relationship."""
    inventory = _sample_inventory()
    return ControlDInventoryPayload(
        user=inventory.user,
        profiles=inventory.profiles,
        devices=(
            inventory.devices[0],
            {
                "device_id": "device-1",
                "PK": "endpoint-pk-1",
                "name": "Chads-Phone",
                "last_activity": 1775067384,
                "profile": {"PK": "profile-1", "name": "Primary"},
                "profile2": {"PK": "profile-2", "name": "Secondary"},
                "parent_device": {
                    "device_id": "router-1",
                    "client_id": "2476a6ca95d7",
                },
            },
        ),
        analytics_clients_by_endpoint={
            "router-1": {
                "clients": {
                    "2476a6ca95d7": {
                        "alias": "Chads-Phone",
                        "host": "KadensSpyPhone",
                        "ip": "192.168.202.244",
                        "mac": "50:eb:71:b6:78:3a",
                    }
                }
            }
        },
    )


def _analytics_only_client_alias_inventory() -> ControlDInventoryPayload:
    """Return inventory where aliasable clients exist only in analytics data."""
    inventory = _sample_inventory()
    return ControlDInventoryPayload(
        user=inventory.user,
        profiles=inventory.profiles,
        devices=(inventory.devices[0],),
        analytics_clients_by_endpoint={
            "router-1": {
                "clients": {
                    "2476a6ca95d7": {
                        "alias": "Chads-Phone",
                        "host": "KadensSpyPhone",
                        "ip": "192.168.202.244",
                        "mac": "50:eb:71:b6:78:3a",
                    }
                }
            }
        },
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
    assert registry.endpoints["device-1"].parent_client_id is None
    assert registry.endpoint_inventory.endpoint_count == 2
    assert registry.endpoint_inventory.client_count == 1
    assert registry.endpoint_inventory.protected_device_count == 3


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


def test_integration_manager_builds_client_alias_targets() -> None:
    """Client alias targets should join devices rows with analytics client data."""
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
        registry = integration_manager.build_registry(_client_alias_inventory())

    target = registry.client_alias_targets[
        build_client_alias_target_key("router-1", "2476a6ca95d7")
    ]
    assert target == ControlDClientAliasTarget(
        target_key=build_client_alias_target_key("router-1", "2476a6ca95d7"),
        source_kind="client",
        endpoint_device_id="device-1",
        endpoint_pk="endpoint-pk-1",
        endpoint_name="Chads-Phone",
        owning_profile_pk="profile-1",
        parent_endpoint_device_id="router-1",
        parent_endpoint_name="Firewalla",
        client_id="2476a6ca95d7",
        client_alias="Chads-Phone",
        client_hostname="KadensSpyPhone",
        client_ip_address="192.168.202.244",
        client_mac_address="50:eb:71:b6:78:3a",
        # This client is a standalone endpoint, so its last-active comes from
        # the endpoint rather than from the analytics row.
        client_last_active=datetime.fromtimestamp(1775067384, UTC),
    )
    assert registry.endpoints["device-1"].parent_client_id == "2476a6ca95d7"


def test_a_standalone_endpoint_client_uses_the_endpoint_last_active() -> None:
    """A promoted client must not report the analytics timestamp.

    Control D attributes a promoted client's traffic to its endpoint and stops
    updating the analytics client row, so that timestamp freezes on the day of
    promotion. On the account this was diagnosed against, all six standalone
    endpoints reported 146 to 174 days ago while their endpoints reported
    activity minutes earlier, for phones in daily use.
    """
    inventory = _client_alias_inventory()
    stale = datetime(2026, 4, 15, 1, 12, 59, tzinfo=UTC)
    inventory = ControlDInventoryPayload(
        user=inventory.user,
        profiles=inventory.profiles,
        devices=inventory.devices,
        analytics_clients_by_endpoint={
            "router-1": {
                "clients": {
                    "2476a6ca95d7": {
                        "alias": "Chads-Phone",
                        "host": "KadensSpyPhone",
                        # Deliberately stale, as the vendor reports it.
                        "lastActivityTime": stale.isoformat(),
                    }
                }
            }
        },
    )

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
        registry = integration_manager.build_registry(inventory)

    target = registry.client_alias_targets[
        build_client_alias_target_key("router-1", "2476a6ca95d7")
    ]

    # The endpoint wins, and the stale analytics value is not what is reported.
    assert target.client_last_active == datetime.fromtimestamp(1775067384, UTC)
    assert target.client_last_active != stale


def test_an_analytics_only_client_still_uses_the_analytics_last_active() -> None:
    """A client with no endpoint of its own has only the analytics source."""
    inventory = _analytics_only_client_alias_inventory()
    seen = datetime(2026, 5, 14, 20, 29, 24, tzinfo=UTC)
    inventory = ControlDInventoryPayload(
        user=inventory.user,
        profiles=inventory.profiles,
        devices=inventory.devices,
        analytics_clients_by_endpoint={
            "router-1": {
                "clients": {
                    "2476a6ca95d7": {
                        "alias": "Chads-Phone",
                        "host": "KadensSpyPhone",
                        "lastActivityTime": seen.isoformat(),
                    }
                }
            }
        },
    )

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
        registry = integration_manager.build_registry(inventory)

    target = registry.client_alias_targets[
        build_client_alias_target_key("router-1", "2476a6ca95d7")
    ]

    assert target.endpoint_device_id is None
    assert target.client_last_active == seen


def test_integration_manager_builds_analytics_only_client_alias_targets() -> None:
    """Analytics-only client rows should still become aliasable service targets."""
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
        registry = integration_manager.build_registry(
            _analytics_only_client_alias_inventory()
        )

    target = registry.client_alias_targets[
        build_client_alias_target_key("router-1", "2476a6ca95d7")
    ]
    assert target.source_kind == "analytics_client"
    assert target.endpoint_device_id is None
    assert target.parent_endpoint_name == "Firewalla"
    assert target.client_hostname == "KadensSpyPhone"
    assert target.client_mac_address == "50:eb:71:b6:78:3a"


def test_endpoint_manager_resolves_analytics_only_client_alias_targets_by_mac() -> None:
    """MAC selectors should resolve analytics-only alias targets."""
    endpoint_manager = EndpointManager()
    runtime = cast(
        Any,
        SimpleNamespace(
            registry=SimpleNamespace(
                client_alias_targets={
                    build_client_alias_target_key("router-1", "2476a6ca95d7"): (
                        ControlDClientAliasTarget(
                            target_key=build_client_alias_target_key(
                                "router-1", "2476a6ca95d7"
                            ),
                            source_kind="analytics_client",
                            endpoint_device_id=None,
                            endpoint_pk=None,
                            endpoint_name="Chads-Phone",
                            owning_profile_pk=None,
                            parent_endpoint_device_id="router-1",
                            parent_endpoint_name="Firewalla-VLAN60",
                            client_id="2476a6ca95d7",
                            client_alias="Chads-Phone",
                            client_hostname="KadensSpyPhone",
                            client_ip_address="192.168.202.244",
                            client_mac_address="50:eb:71:b6:78:3a",
                        )
                    )
                }
            )
        ),
    )
    endpoint_manager.attach_runtime(runtime)

    assert (
        endpoint_manager.resolve_client_alias_target(
            endpoint_mac="50-EB-71-B6-78-3A"
        ).client_id
        == "2476a6ca95d7"
    )


def test_endpoint_manager_resolves_client_alias_targets_by_supported_selectors() -> (
    None
):
    """Client alias lookups should resolve by MAC, name, hostname, and IP."""
    endpoint_manager = EndpointManager()
    runtime = cast(
        Any,
        SimpleNamespace(
            registry=SimpleNamespace(
                client_alias_targets={
                    build_client_alias_target_key("router-1", "2476a6ca95d7"): (
                        ControlDClientAliasTarget(
                            target_key=build_client_alias_target_key(
                                "router-1", "2476a6ca95d7"
                            ),
                            source_kind="client",
                            endpoint_device_id="device-1",
                            endpoint_pk="endpoint-pk-1",
                            endpoint_name="Chads-Phone",
                            owning_profile_pk="profile-1",
                            parent_endpoint_device_id="router-1",
                            parent_endpoint_name="Firewalla-VLAN60",
                            client_id="2476a6ca95d7",
                            client_alias="Chads-Phone",
                            client_hostname="KadensSpyPhone",
                            client_ip_address="192.168.202.244",
                            client_mac_address="50:eb:71:b6:78:3a",
                        )
                    )
                }
            )
        ),
    )
    endpoint_manager.attach_runtime(runtime)

    assert (
        endpoint_manager.resolve_client_alias_target(
            endpoint_mac="50-EB-71-B6-78-3A"
        ).client_id
        == "2476a6ca95d7"
    )
    assert (
        endpoint_manager.resolve_client_alias_target(
            endpoint_name="Chads-Phone"
        ).client_id
        == "2476a6ca95d7"
    )
    assert (
        endpoint_manager.resolve_client_alias_target(
            endpoint_hostname="KadensSpyPhone"
        ).client_id
        == "2476a6ca95d7"
    )
    assert (
        endpoint_manager.resolve_client_alias_target(
            endpoint_ip="192.168.202.244"
        ).client_id
        == "2476a6ca95d7"
    )


def test_endpoint_manager_rejects_ambiguous_client_alias_targets() -> None:
    """Client alias lookups should reject ambiguous convenience selectors."""
    endpoint_manager = EndpointManager()
    runtime = cast(
        Any,
        SimpleNamespace(
            registry=SimpleNamespace(
                client_alias_targets={
                    build_client_alias_target_key("router-1", "client-1"): (
                        ControlDClientAliasTarget(
                            target_key=build_client_alias_target_key(
                                "router-1", "client-1"
                            ),
                            source_kind="client",
                            endpoint_device_id="device-1",
                            endpoint_pk="endpoint-pk-1",
                            endpoint_name="Chads-Phone",
                            owning_profile_pk="profile-1",
                            parent_endpoint_device_id="router-1",
                            parent_endpoint_name="Firewalla-VLAN60",
                            client_id="client-1",
                            client_hostname="duplicate-host",
                        )
                    ),
                    build_client_alias_target_key("router-2", "client-2"): (
                        ControlDClientAliasTarget(
                            target_key=build_client_alias_target_key(
                                "router-2", "client-2"
                            ),
                            source_kind="client",
                            endpoint_device_id="device-2",
                            endpoint_pk="endpoint-pk-2",
                            endpoint_name="Paytons-Phone",
                            owning_profile_pk="profile-2",
                            parent_endpoint_device_id="router-2",
                            parent_endpoint_name="Firewalla-VLAN70",
                            client_id="client-2",
                            client_hostname="duplicate-host",
                        )
                    ),
                }
            )
        ),
    )
    endpoint_manager.attach_runtime(runtime)

    with pytest.raises(ValueError, match="Ambiguous"):
        endpoint_manager.resolve_client_alias_target(endpoint_hostname="duplicate-host")

    assert (
        endpoint_manager.resolve_client_alias_target(
            endpoint_hostname="duplicate-host",
            parent_endpoint_name="Firewalla-VLAN60",
        ).client_id
        == "client-1"
    )


def test_endpoint_manager_resolves_a_client_id_shared_mac_pair_unambiguously() -> None:
    """Two clients under one endpoint share a MAC, so only the client id selects one."""
    endpoint_manager = EndpointManager()
    shared = "3c:5c:c4:07:7c:a3"

    def _target(client_id: str) -> ControlDClientAliasTarget:
        return ControlDClientAliasTarget(
            target_key=build_client_alias_target_key("router-1", client_id),
            source_kind="analytics_client",
            endpoint_device_id=None,
            endpoint_pk=None,
            endpoint_name=None,
            owning_profile_pk=None,
            parent_endpoint_device_id="router-1",
            parent_endpoint_name="Firewalla-VLAN60",
            client_id=client_id,
            client_hostname="KadensSpyPhone",
            client_mac_address=shared,
        )

    runtime = cast(
        Any,
        SimpleNamespace(
            registry=SimpleNamespace(
                client_alias_targets={
                    build_client_alias_target_key("router-1", "04070f91bf7d"): (
                        _target("04070f91bf7d")
                    ),
                    build_client_alias_target_key("router-1", "d18cc9582f25"): (
                        _target("d18cc9582f25")
                    ),
                }
            )
        ),
    )
    endpoint_manager.attach_runtime(runtime)

    with pytest.raises(ValueError, match="Ambiguous"):
        endpoint_manager.resolve_client_alias_target(endpoint_mac=shared)

    assert (
        endpoint_manager.resolve_client_alias_target(client_id="d18cc9582f25").client_id
        == "d18cc9582f25"
    )


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


def test_integration_manager_keeps_automatic_and_manual_services_exclusive() -> None:
    """Manual categories should not union with automatic explicit service rows."""
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
                services=(
                    {
                        "PK": "amazonmusic",
                        "name": "Amazon Music",
                        "category": "audio",
                        "action": {"do": 1, "status": 1},
                    },
                    {
                        "PK": "facebook",
                        "name": "Facebook",
                        "category": "social",
                        "action": {"do": 0, "status": 0},
                    },
                )
            )
        },
        option_catalog=OPTION_CATALOG,
        service_categories=(
            {"PK": "audio", "name": "Audio", "count": 1},
            {"PK": "social", "name": "Social", "count": 1},
        ),
        service_catalog=(
            {"PK": "amazonmusic", "name": "Amazon Music", "category": "audio"},
            {"PK": "facebook", "name": "Facebook", "category": "social"},
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
                    options=ControlDOptions(
                        profile_policies={
                            "profile-1": ControlDProfilePolicy(
                                allowed_service_categories=frozenset({"audio"}),
                            )
                        }
                    )
                ),
            )
        )
        registry = integration_manager.build_registry(inventory)

    assert set(registry.services_by_profile["profile-1"]) == {"amazonmusic"}
    assert (
        registry.services_by_profile["profile-1"]["amazonmusic"].current_mode
        == "bypassed"
    )


def test_integration_manager_logs_malformed_service_catalog_rows(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed service catalog rows should log enough setup context to debug."""
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
                services=(
                    {
                        "PK": "amazonmusic",
                        "name": "Amazon Music",
                        "category": "audio",
                        "action": {"do": 1, "status": 1},
                    },
                )
            )
        },
        option_catalog=OPTION_CATALOG,
        service_categories=({"PK": "audio", "name": "Audio", "count": 1},),
        service_catalog=(
            {"PK": "amazonmusic", "name": "Amazon Music", "category": None},
        ),
    )

    with (
        patch.object(device_manager, "sync_registry"),
        patch.object(entity_manager, "sync_registry"),
    ):
        integration_manager.attach_runtime(
            cast(Any, SimpleNamespace(options=ControlDOptions()))
        )
        with (
            caplog.at_level(
                logging.DEBUG,
                logger="custom_components.controld_manager.managers.integration_manager",
            ),
            pytest.raises(ValueError, match="category"),
        ):
            integration_manager.build_registry(inventory)

    assert (
        "Service normalization failed while building automatic service row"
        in caplog.text
    )
    assert "profile-1" in caplog.text
    assert "category" in caplog.text
    assert "source=catalog" in caplog.text


def test_integration_manager_accepts_numeric_live_service_pk() -> None:
    """Live service rows should accept numeric IDs and join to catalog rows."""
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
                services=(
                    {
                        "PK": 1688,
                        "name": 1688,
                        "category": "shop",
                        "action": {"do": 0, "status": 1},
                    },
                )
            )
        },
        option_catalog=OPTION_CATALOG,
        service_categories=({"PK": "shop", "name": "Shop", "count": 1},),
        service_catalog=(
            {
                "PK": 1688,
                "name": "1688",
                "category": "shop",
                "unlock_location": "JFK",
            },
        ),
    )

    with (
        patch.object(device_manager, "sync_registry"),
        patch.object(entity_manager, "sync_registry"),
    ):
        integration_manager.attach_runtime(
            cast(Any, SimpleNamespace(options=ControlDOptions()))
        )
        registry = integration_manager.build_registry(inventory)

    service_row = registry.services_by_profile["profile-1"]["1688"]
    assert service_row.service_pk == "1688"
    assert service_row.name == "1688"
    assert service_row.category_pk == "shop"
    assert service_row.category_name == "Shop"
    assert service_row.enabled is True
    assert service_row.current_mode == "blocked"


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
                schedule_write_verification=lambda: None,
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


async def test_service_write_payload_matches_browser_contract() -> None:
    """Service writes should match the browser-verified service API contract."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_set_profile_service(
                "profile-1",
                "amazonmusic",
                enabled=True,
                action_do=3,
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/services/amazonmusic",
        {"status": 1, "do": 3},
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


async def test_rule_rich_write_payload_supports_redirect_targets() -> None:
    """Rich rule writes should forward explicit redirect targets when supplied."""
    async with ClientSession() as session:
        client = ControlDAPIClient("token-value", session)

        with patch.object(client, "_async_request", new=AsyncMock()) as async_request:
            await client.async_update_profile_rule_rich(
                "profile-1",
                "example.com",
                enabled=True,
                action_do=3,
                group_pk=None,
                ttl=None,
                comment="",
                via="WFR",
            )

    async_request.assert_awaited_once_with(
        "PUT",
        "/profiles/profile-1/rules",
        {
            "do": 3,
            "status": 1,
            "via": "WFR",
            "via_v6": "-1",
            "hostnames": ["example.com"],
            "group": 0,
            "comment": "",
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
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


async def test_setup_entry_populates_client_alias_targets_from_analytics_clients(
    hass,
) -> None:
    """Setup should populate client alias targets from analytics client reads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value"},
        unique_id="user-123",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=_client_alias_inventory()),
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(
                return_value={
                    "router-1": {
                        "clients": {
                            "2476a6ca95d7": {
                                "alias": "Chads-Phone",
                                "host": "KadensSpyPhone",
                                "ip": "192.168.202.244",
                                "mac": "50:eb:71:b6:78:3a",
                            }
                        }
                    }
                }
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime = entry.runtime_data
    target = runtime.registry.client_alias_targets[
        build_client_alias_target_key("router-1", "2476a6ca95d7")
    ]
    assert target.endpoint_device_id == "device-1"
    assert target.parent_endpoint_name == "Firewalla"
    assert target.client_hostname == "KadensSpyPhone"


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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
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


async def test_coordinator_logs_normalization_stage_failure(hass, caplog) -> None:
    """Normalization failures should emit a coordinator debug traceback."""
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime = entry.runtime_data
    runtime.options = ControlDOptions(
        profile_policies={
            "profile-1": ControlDProfilePolicy(
                allowed_service_categories=frozenset({SERVICE_SELECTOR_AUTOMATIC}),
            )
        }
    )

    with (
        patch.object(
            runtime.client,
            "async_get_inventory",
            new=AsyncMock(return_value=_sample_inventory()),
        ),
        patch.object(
            runtime.client,
            "async_get_profile_detail",
            new=AsyncMock(
                return_value=ControlDProfileDetailPayload(
                    services=(
                        {
                            "PK": "amazonmusic",
                            "name": "Amazon Music",
                            "category": "audio",
                            "action": {"do": 1, "status": 1},
                        },
                    )
                )
            ),
        ),
        patch.object(
            runtime.client,
            "async_get_profile_option_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            runtime.client,
            "async_get_service_categories",
            new=AsyncMock(return_value=[{"PK": "audio", "name": "Audio", "count": 1}]),
        ),
        patch.object(
            runtime.client,
            "async_get_service_catalog",
            new=AsyncMock(
                return_value=[
                    {"PK": "amazonmusic", "name": "Amazon Music", "category": None}
                ]
            ),
        ),
        patch.object(
            runtime.client,
            "async_get_analytics_clients",
            new=AsyncMock(return_value={}),
        ),
        caplog.at_level(
            logging.DEBUG,
            logger="custom_components.controld_manager.coordinator",
        ),
        pytest.raises(UpdateFailed, match="normalization failed"),
    ):
        await runtime.active_coordinator._async_update_data()

    assert "Starting Control D refresh" in caplog.text
    assert "Fetched service metadata" in caplog.text
    assert "Control D refresh failed during normalization" in caplog.text


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
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
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
        patch.object(
            runtime.client,
            "async_get_account_analytics",
            new=AsyncMock(return_value=_sample_account_analytics()),
        ),
        patch.object(
            runtime.client,
            "async_get_profile_analytics",
            new=AsyncMock(
                side_effect=lambda _endpoint, profile_pk, **_kwargs: (
                    _sample_profile_analytics(profile_pk)
                )
            ),
        ),
        patch.object(
            runtime.client,
            "async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            runtime.client,
            "async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            runtime.client,
            "async_get_analytics_clients",
            new=AsyncMock(return_value={}),
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


async def test_setup_entry_migrates_empty_service_categories_to_automatic(hass) -> None:
    """Setup should persist the automatic sentinel for empty legacy service state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value"},
        options={
            "profile_policies": {"profile-1": {"allowed_service_categories": ["audio"]}}
        },
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    profile_1_policy = entry.options["profile_policies"]["profile-1"]
    profile_2_policy = entry.options["profile_policies"]["profile-2"]
    assert profile_1_policy["allowed_service_categories"] == ["audio"]
    assert profile_2_policy["allowed_service_categories"] == [
        SERVICE_SELECTOR_AUTOMATIC
    ]
    assert "service_exposure_mode" not in profile_1_policy
    assert "service_exposure_mode" not in profile_2_policy
    assert "auto_enable_service_switches" not in profile_1_policy
    assert "auto_enable_service_switches" not in profile_2_policy


async def test_setup_entry_migrates_legacy_automatic_mode_without_categories(
    hass,
) -> None:
    """Migrate legacy automatic mode without categories to the selector.

    The migrated value should be the automatic sentinel stored in the selector.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value"},
        options={
            "profile_policies": {
                "profile-1": {"service_exposure_mode": "automatic"},
            }
        },
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    profile_1_policy = entry.options["profile_policies"]["profile-1"]
    assert profile_1_policy["allowed_service_categories"] == [
        SERVICE_SELECTOR_AUTOMATIC
    ]
    assert "service_exposure_mode" not in profile_1_policy
    assert "auto_enable_service_switches" not in profile_1_policy


async def test_coordinator_requests_services_for_automatic_profiles(hass) -> None:
    """Automatic service mode should request profile service details."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value"},
        options={
            "profile_policies": {
                "profile-1": {
                    "allowed_service_categories": [SERVICE_SELECTOR_AUTOMATIC]
                },
                "profile-2": {"service_exposure_mode": SERVICE_EXPOSURE_MANUAL},
            }
        },
        unique_id="user-123",
    )
    entry.add_to_hass(hass)

    detail_mock = AsyncMock(return_value=ControlDProfileDetailPayload())
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
            new=detail_mock,
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_analytics_clients",
            new=AsyncMock(return_value={}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    detail_mock.assert_has_awaits(
        [
            call("profile-1", include_services=True, include_rules=False),
            call("profile-2", include_services=False, include_rules=False),
        ],
        any_order=True,
    )


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
                FIELD_EXPOSE_ALL_ACTIVE_SERVICES: True,
                "endpoint_sensors_enabled": True,
                "endpoint_inactivity_threshold_minutes": 20,
                "allowed_service_categories": [],
                FIELD_EXPOSE_ALL_CUSTOM_RULES: True,
                "exposed_custom_rules": [],
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
        "allowed_service_categories": [SERVICE_SELECTOR_AUTOMATIC],
        "exposed_custom_rules": ["system:all_rules"],
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


def _client_delete_runtime(
    targets: dict[str, ControlDClientAliasTarget],
    *,
    deleted_count: int,
) -> SimpleNamespace:
    """Return a runtime stub whose client records the destructive deletes.

    The stubbed methods return what the real client methods return: the unwrapped
    `body`, not the outer envelope.
    """
    return SimpleNamespace(
        client=SimpleNamespace(
            async_delete_analytics_clients=AsyncMock(
                return_value={"deletedCount": deleted_count, "deletedClients": []}
            ),
            async_delete_analytics_client_history=AsyncMock(
                return_value={"success": True}
            ),
        ),
        registry=SimpleNamespace(
            user=SimpleNamespace(stats_endpoint="america"),
            client_alias_targets=dict(targets),
        ),
        active_coordinator=SimpleNamespace(schedule_write_verification=lambda: None),
    )


def _delete_target(parent: str, client_id: str) -> ControlDClientAliasTarget:
    """Return one analytics-only client alias target under a parent endpoint."""
    return ControlDClientAliasTarget(
        target_key=build_client_alias_target_key(parent, client_id),
        source_kind="analytics_client",
        endpoint_device_id=None,
        endpoint_pk=None,
        endpoint_name=None,
        owning_profile_pk=None,
        parent_endpoint_device_id=parent,
        parent_endpoint_name="Firewalla-VLAN60",
        client_id=client_id,
    )


async def test_endpoint_manager_deletes_clients_grouped_by_parent() -> None:
    """One verb call per parent, the API's own count returned, rows dropped.

    The verb takes a parent with many client ids, so grouping keeps the call count
    at the number of parents instead of the number of clients.
    """
    first = _delete_target("router-1", "c-1")
    second = _delete_target("router-1", "c-2")
    third = _delete_target("router-2", "c-3")
    runtime = _client_delete_runtime(
        {target.target_key: target for target in (first, second, third)},
        deleted_count=2,
    )
    endpoint_manager = EndpointManager()
    endpoint_manager.attach_runtime(cast(Any, runtime))

    deleted = await endpoint_manager.async_delete_clients(
        (first, second, third), delete_history=True
    )

    assert deleted == 4  # two parents x deletedCount 2
    assert runtime.client.async_delete_analytics_clients.await_count == 2
    assert runtime.client.async_delete_analytics_client_history.await_count == 2
    assert runtime.registry.client_alias_targets == {}
    assert runtime.client.async_delete_analytics_clients.await_args_list[0].kwargs[
        "client_ids"
    ] == ["c-1", "c-2"]


async def test_endpoint_manager_keeps_history_when_asked_to() -> None:
    """delete_history=False removes the rows and leaves the history alone."""
    target = _delete_target("router-1", "c-1")
    runtime = _client_delete_runtime({target.target_key: target}, deleted_count=1)
    endpoint_manager = EndpointManager()
    endpoint_manager.attach_runtime(cast(Any, runtime))

    deleted = await endpoint_manager.async_delete_clients(
        (target,), delete_history=False
    )

    assert deleted == 1
    runtime.client.async_delete_analytics_clients.assert_awaited_once()
    runtime.client.async_delete_analytics_client_history.assert_not_awaited()
    assert runtime.registry.client_alias_targets == {}


def _profile_write_runtime(
    endpoint: ControlDEndpointSummary,
) -> SimpleNamespace:
    """Return a runtime stub whose registry holds one endpoint."""
    return SimpleNamespace(
        client=SimpleNamespace(
            async_set_endpoint_profile=AsyncMock(return_value=None),
            async_clear_endpoint_secondary_profile=AsyncMock(return_value=None),
        ),
        registry=SimpleNamespace(
            user=SimpleNamespace(stats_endpoint="america"),
            endpoints={endpoint.device_id: endpoint},
            profiles={},
        ),
        active_coordinator=SimpleNamespace(schedule_write_verification=lambda: None),
    )


async def test_a_profile_write_updates_the_registry_immediately() -> None:
    """A following call must read the value this one just wrote.

    The pre-check, the no-op check, and the undo all read the runtime registry,
    so leaving it stale until the next refresh makes a back-to-back write report
    state that is no longer true -- and derive an undo from it.
    """
    endpoint = ControlDEndpointSummary(
        device_id="ep-1",
        endpoint_pk="ep-1",
        name="Endpoint-Test",
        attached_profiles=(ControlDAttachedProfile(profile_pk="primary-a"),),
    )
    runtime = _profile_write_runtime(endpoint)
    manager = EndpointManager()
    manager.attach_runtime(cast(Any, runtime))

    # Attach a secondary.
    await manager.async_set_endpoint_profiles(
        (endpoint,), profile_pk=None, profile2_pk="secondary-b", clear_profile2=False
    )
    assert runtime.registry.endpoints["ep-1"].secondary_profile_pk == "secondary-b"

    # Replace it, reading the registry as the next tool call would. The value
    # must be the one just written, not the one from before the first write.
    current = runtime.registry.endpoints["ep-1"]
    assert current.secondary_profile_pk == "secondary-b"
    await manager.async_set_endpoint_profiles(
        (current,), profile_pk=None, profile2_pk="secondary-c", clear_profile2=False
    )
    assert runtime.registry.endpoints["ep-1"].secondary_profile_pk == "secondary-c"

    # Clearing removes it, and the primary is untouched throughout.
    await manager.async_set_endpoint_profiles(
        (runtime.registry.endpoints["ep-1"],),
        profile_pk=None,
        profile2_pk=None,
        clear_profile2=True,
    )
    cleared = runtime.registry.endpoints["ep-1"]
    assert cleared.secondary_profile_pk is None
    assert cleared.owning_profile_pk == "primary-a"


async def test_a_primary_profile_write_updates_the_registry_immediately() -> None:
    """A primary change is reflected without waiting for the refresh."""
    endpoint = ControlDEndpointSummary(
        device_id="ep-2",
        endpoint_pk="ep-2",
        name="Endpoint-Test",
        attached_profiles=(ControlDAttachedProfile(profile_pk="primary-a"),),
    )
    runtime = _profile_write_runtime(endpoint)
    manager = EndpointManager()
    manager.attach_runtime(cast(Any, runtime))

    await manager.async_set_endpoint_profiles(
        (endpoint,), profile_pk="primary-b", profile2_pk=None, clear_profile2=False
    )

    assert runtime.registry.endpoints["ep-2"].owning_profile_pk == "primary-b"


async def test_a_description_write_updates_the_registry_immediately() -> None:
    """The new note is readable by the next call rather than after a refresh."""
    endpoint = ControlDEndpointSummary(
        device_id="ep-3",
        endpoint_pk="ep-3",
        name="Endpoint-Test",
        attached_profiles=(ControlDAttachedProfile(profile_pk="primary-a"),),
        description="before",
    )
    runtime = SimpleNamespace(
        client=SimpleNamespace(
            async_set_endpoint_description=AsyncMock(return_value=None)
        ),
        registry=SimpleNamespace(endpoints={endpoint.device_id: endpoint}),
        active_coordinator=SimpleNamespace(schedule_write_verification=lambda: None),
    )
    manager = EndpointManager()
    manager.attach_runtime(cast(Any, runtime))

    await manager.async_set_endpoint_descriptions((endpoint,), "after")
    assert runtime.registry.endpoints["ep-3"].description == "after"

    # An empty note clears it, matching what the API stores.
    await manager.async_set_endpoint_descriptions(
        (runtime.registry.endpoints["ep-3"],), ""
    )
    assert runtime.registry.endpoints["ep-3"].description is None


async def test_a_primary_write_keeps_the_secondary_and_the_list_agreeing() -> None:
    """The enforced-profile list is the one stored fact, so it cannot drift.

    `owning_profile_pk` and `secondary_profile_pk` are read from that list, so a
    write has to move the list itself. Updating only the scalars left it stale,
    which made one endpoint row report two different primaries and made
    profile-filtered reads miss the profile that was just attached.
    """
    endpoint = ControlDEndpointSummary(
        device_id="ep-4",
        endpoint_pk="ep-4",
        name="Endpoint-Test",
        attached_profiles=(
            ControlDAttachedProfile(profile_pk="primary-a"),
            ControlDAttachedProfile(profile_pk="secondary-a"),
        ),
    )
    runtime = _profile_write_runtime(endpoint)
    manager = EndpointManager()
    manager.attach_runtime(cast(Any, runtime))

    await manager.async_set_endpoint_profiles(
        (endpoint,), profile_pk="primary-b", profile2_pk=None, clear_profile2=False
    )

    written = runtime.registry.endpoints["ep-4"]
    assert written.owning_profile_pk == "primary-b"
    # Replacing the primary must not disturb the second slot.
    assert written.secondary_profile_pk == "secondary-a"
    assert [entry.profile_pk for entry in written.attached_profiles] == [
        "primary-b",
        "secondary-a",
    ]


async def test_a_profile_name_is_resolved_from_the_registry() -> None:
    """The list carries names too, so a row needs no second lookup to show one."""
    endpoint = ControlDEndpointSummary(
        device_id="ep-5",
        endpoint_pk="ep-5",
        name="Endpoint-Test",
        attached_profiles=(ControlDAttachedProfile(profile_pk="primary-a"),),
    )
    runtime = _profile_write_runtime(endpoint)
    runtime.registry.profiles = {
        "primary-b": SimpleNamespace(profile_pk="primary-b", name="Kids")
    }
    manager = EndpointManager()
    manager.attach_runtime(cast(Any, runtime))

    await manager.async_set_endpoint_profiles(
        (endpoint,), profile_pk="primary-b", profile2_pk=None, clear_profile2=False
    )

    written = runtime.registry.endpoints["ep-5"]
    assert written.attached_profiles[0].name == "Kids"
