"""Entity and service tests for Control D Manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.api import ControlDApiConnectionError
from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    DOMAIN,
    SERVICE_FIELD_MINUTES,
    SERVICE_PAUSE_PROFILE,
    SERVICE_RESUME_PROFILE,
)
from custom_components.controld_manager.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.controld_manager.models import (
    ControlDInventoryPayload,
    ControlDOptions,
    ControlDProfileDetailPayload,
    ControlDProfilePolicy,
)

SERVICE_CATEGORIES = [{"PK": "audio", "name": "Audio", "count": 18}]
SERVICE_CATALOG = [
    {
        "PK": "amazonmusic",
        "name": "Amazon Music",
        "category": "audio",
        "warning": "",
        "unlock_location": "JFK",
    }
]


def _inventory(instance_id: str, owning_profile_pk: str) -> ControlDInventoryPayload:
    """Return a representative inventory payload for Phase 4 tests."""
    secondary_profile_pk = (
        "profile-2" if owning_profile_pk == "profile-1" else "profile-1"
    )
    return ControlDInventoryPayload(
        user={
            "id": instance_id,
            "PK": f"account-{instance_id}",
            "stats_endpoint": "america",
            "safe_countries": ["US", "CA"],
        },
        profiles=(
            {"PK": "profile-1", "name": "Primary", "disable": None},
            {"PK": "profile-2", "name": "Secondary", "disable": None},
        ),
        devices=(
            {
                "device_id": "router-1",
                "PK": "endpoint-pk-router-1",
                "name": "Firewalla",
                "last_activity": 1775067385,
                "profile": {"PK": owning_profile_pk, "name": "Primary"},
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
                "profile": {"PK": owning_profile_pk, "name": "Primary"},
                "profile2": {"PK": secondary_profile_pk, "name": "Secondary"},
                "parent_device": {"device_id": "router-1"},
            },
        ),
    )


async def _async_setup_entry(
    hass, entry: MockConfigEntry, inventory: ControlDInventoryPayload
) -> None:
    """Set up a mock config entry with a patched inventory fetch."""
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=inventory),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(
                side_effect=lambda profile_pk, include_services, include_rules: (
                    _detail_payload(
                        profile_pk,
                        include_services=include_services,
                        include_rules=include_rules,
                    )
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=SERVICE_CATEGORIES),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=SERVICE_CATALOG),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _detail_payload(
    profile_pk: str, *, include_services: bool, include_rules: bool
) -> ControlDProfileDetailPayload:
    """Return representative profile detail payloads for Phase 5 surfaces."""
    filters = (
        {
            "PK": "ads",
            "name": "Ads & Trackers",
            "levels": [
                {"title": "Relaxed", "name": "ads_small", "status": 1},
                {"title": "Balanced", "name": "ads_medium", "status": 0},
                {"title": "Strict", "name": "ads", "status": 0},
            ],
            "action": {"do": 0, "status": 1, "lvl": "ads_small"},
            "status": 1,
        },
        {
            "PK": "ai_malware",
            "name": "AI Malware",
            "levels": [],
            "action": {"do": 0, "status": 1},
            "status": 1,
        },
        {
            "PK": "social",
            "name": "Social Networks",
            "levels": [],
            "action": {"do": 0, "status": 0},
            "status": 0,
        },
    )
    services = (
        (
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "category": "audio",
                "warning": "",
                "unlock_location": "JFK",
                "action": {"do": 1, "status": 1},
            },
        )
        if include_services and profile_pk == "profile-1"
        else ()
    )
    groups = (
        ({"PK": 1, "group": "Allow folder", "action": {"status": 1, "do": 1}},)
        if include_rules and profile_pk == "profile-1"
        else ()
    )
    rules = (
        (
            {
                "PK": "example.com",
                "order": 1,
                "group": 0,
                "action": {"do": 0, "status": 1},
            },
            {
                "PK": "example2.com",
                "order": 1,
                "group": 1,
                "action": {"do": 1, "status": 1},
            },
        )
        if include_rules and profile_pk == "profile-1"
        else ()
    )
    return ControlDProfileDetailPayload(
        filters=filters,
        services=services,
        groups=groups,
        rules=rules,
    )


async def test_phase4_entities_are_created_and_attached(hass) -> None:
    """Default entities should follow the approved Phase 5 exposure contract."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    profile_count_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "user-123::instance::system::profile_count"
    )
    endpoint_count_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "user-123::instance::system::endpoint_count"
    )
    status_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "user-123::instance::system::status"
    )
    sync_button_entity_id = entity_registry.async_get_entity_id(
        "button", DOMAIN, "user-123::instance::system::sync"
    )
    pause_switch_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::paused"
    )
    ads_filter_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::filter::ads"
    )
    ads_mode_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::filter_mode::ads"
    )
    endpoint_status_entity_id = entity_registry.async_get_entity_id(
        "binary_sensor", DOMAIN, "user-123::endpoint::device-1::status"
    )
    service_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::service::amazonmusic"
    )
    social_filter_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::filter::social"
    )

    assert profile_count_entity_id is not None
    assert endpoint_count_entity_id is not None
    assert status_entity_id is not None
    assert sync_button_entity_id is not None
    assert pause_switch_entity_id is not None
    assert ads_filter_entity_id is not None
    assert ads_mode_entity_id is not None
    assert endpoint_status_entity_id is None
    assert service_entity_id is None
    assert hass.states.get(profile_count_entity_id).state == "2"
    assert hass.states.get(endpoint_count_entity_id).state == "3"
    assert hass.states.get(status_entity_id).state == "healthy"
    assert hass.states.get(status_entity_id).name == "Account Status"
    assert hass.states.get(endpoint_count_entity_id).name == "Account Endpoint count"
    assert hass.states.get(profile_count_entity_id).name == "Account Profile count"
    assert hass.states.get(sync_button_entity_id).name == "Account Sync now"
    assert (
        hass.states.get(status_entity_id).attributes["last_successful_refresh"]
        is not None
    )
    assert (
        hass.states.get(status_entity_id).attributes["consecutive_failed_refreshes"]
        == 0
    )
    assert "last_refresh_error" not in hass.states.get(status_entity_id).attributes
    assert "router_client_count" not in hass.states.get(status_entity_id).attributes

    profile_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    account_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "instance::user-123")}
    )
    assert profile_device is not None
    assert account_device is not None
    assert account_device.name == "Account"
    ads_filter_entry = entity_registry.async_get(ads_filter_entity_id)
    social_filter_entry = entity_registry.async_get(social_filter_entity_id)
    assert ads_filter_entry is not None
    assert social_filter_entry is not None
    assert ads_filter_entry.device_id == profile_device.id
    assert social_filter_entry.disabled_by is not None
    assert (
        hass.states.get(ads_filter_entity_id).name == "Primary Filters / Ads & Trackers"
    )


async def test_phase5_policy_enabled_entities_are_created_and_attached(hass) -> None:
    """Opted-in endpoint, service, and rule entities should be generated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    endpoint_sensors_enabled=True,
                    allowed_service_categories=frozenset({"audio"}),
                    exposed_custom_rules=frozenset(
                        {"rule:root|example.com", "group:1"}
                    ),
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    status_entity_id = entity_registry.async_get_entity_id(
        "binary_sensor", DOMAIN, "user-123::endpoint::device-1::status"
    )
    service_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::service::amazonmusic"
    )
    rule_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::rule::root|example.com"
    )
    grouped_rule_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::rule::group:1|example2.com"
    )
    profile_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )

    assert status_entity_id is not None
    assert service_entity_id is not None
    assert rule_entity_id is not None
    assert grouped_rule_entity_id is not None
    status_entry = entity_registry.async_get(status_entity_id)
    service_entry = entity_registry.async_get(service_entity_id)
    assert status_entry is not None
    assert service_entry is not None
    assert profile_device is not None
    assert status_entry.device_id == profile_device.id
    assert service_entry.disabled_by is not None
    assert (
        hass.states.get(rule_entity_id).name == "Primary Rules / Domain / example.com"
    )


async def test_endpoint_roaming_reassigns_device_attachment(hass) -> None:
    """Endpoint status attachment should move when owning profile changes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(endpoint_sensors_enabled=True),
                "profile-2": ControlDProfilePolicy(endpoint_sensors_enabled=True),
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(
                side_effect=[
                    _inventory("user-123", "profile-1"),
                    _inventory("user-123", "profile-2"),
                ]
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(
                side_effect=lambda profile_pk, include_services, include_rules: (
                    _detail_payload(
                        profile_pk,
                        include_services=include_services,
                        include_rules=include_rules,
                    )
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=SERVICE_CATEGORIES),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=SERVICE_CATALOG),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    status_entity_id = entity_registry.async_get_entity_id(
        "binary_sensor", DOMAIN, "user-123::endpoint::device-1::status"
    )
    endpoint_entry = entity_registry.async_get(status_entity_id)
    secondary_profile_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-2")}
    )

    assert endpoint_entry is not None
    assert secondary_profile_device is not None
    assert endpoint_entry.device_id == secondary_profile_device.id


async def test_excluded_profile_device_is_removed_from_registry(hass) -> None:
    """Excluding a profile should remove its managed device entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    device_registry = dr.async_get(hass)
    managed_profile_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-2")}
    )
    assert managed_profile_device is not None

    runtime = entry.runtime_data
    runtime.options = ControlDOptions(
        profile_policies={
            "profile-2": ControlDProfilePolicy(managed_in_home_assistant=False)
        }
    )

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=_inventory("user-123", "profile-1")),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(
                side_effect=lambda profile_pk, include_services, include_rules: (
                    _detail_payload(
                        profile_pk,
                        include_services=include_services,
                        include_rules=include_rules,
                    )
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=SERVICE_CATEGORIES),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=SERVICE_CATALOG),
        ),
    ):
        await runtime.active_coordinator.async_refresh()
        await hass.async_block_till_done()

    removed_profile_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-2")}
    )
    assert removed_profile_device is None


async def test_sync_button_runs_manual_refresh(hass) -> None:
    """The account sync button should trigger an on-demand refresh."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    sync_button_entity_id = entity_registry.async_get_entity_id(
        "button", DOMAIN, "user-123::instance::system::sync"
    )
    runtime = entry.runtime_data

    with patch.object(
        runtime.active_coordinator,
        "async_run_manual_refresh",
        new=AsyncMock(),
    ) as async_run_manual_refresh:
        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: sync_button_entity_id},
            blocking=True,
        )

    async_run_manual_refresh.assert_awaited_once()


async def test_status_sensor_tracks_degraded_and_problem_states(hass) -> None:
    """Repeated failed refreshes should escalate the account health state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    status_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "user-123::instance::system::status"
    )
    runtime = entry.runtime_data

    with patch(
        "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
        new=AsyncMock(
            side_effect=[
                ControlDApiConnectionError("first failure"),
                ControlDApiConnectionError("second failure"),
            ]
        ),
    ):
        await runtime.active_coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(status_entity_id).state == "degraded"
        assert (
            hass.states.get(status_entity_id).attributes["consecutive_failed_refreshes"]
            == 1
        )
        assert (
            hass.states.get(status_entity_id).attributes["last_refresh_error"]
            == "Unable to reach the Control D API"
        )

        await runtime.active_coordinator.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(status_entity_id).state == "problem"
    assert (
        hass.states.get(status_entity_id).attributes["consecutive_failed_refreshes"]
        == 2
    )


async def test_pause_service_targets_profile_from_entity_id(hass) -> None:
    """The pause service should resolve a profile switch target safely."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    pause_switch_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::paused"
    )
    runtime = entry.runtime_data
    runtime.client.async_set_profile_pause_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PAUSE_PROFILE,
        {ATTR_ENTITY_ID: [pause_switch_entity_id], SERVICE_FIELD_MINUTES: 30},
        blocking=True,
    )

    runtime.client.async_set_profile_pause_until.assert_awaited_once()
    profile_pk, disable_ttl = (
        runtime.client.async_set_profile_pause_until.await_args.args
    )
    assert profile_pk == "profile-1"
    assert isinstance(disable_ttl, int)


async def test_resume_service_supports_instance_target_by_config_entry_id(hass) -> None:
    """The resume service should target all profiles when a config entry is selected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_pause_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESUME_PROFILE,
        {"config_entry_name": "Control D Home"},
        blocking=True,
    )

    assert runtime.client.async_set_profile_pause_until.await_count == 2


async def test_pause_service_rejects_mixed_instance_targets(hass) -> None:
    """The pause service should reject targets that span multiple instances."""
    entry_one = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-one", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    entry_two = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-two", "entry_name": "Control D Cabin"},
        unique_id="user-456",
        title="Control D Cabin",
    )
    entry_one.add_to_hass(hass)
    entry_two.add_to_hass(hass)

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(
                side_effect=[
                    _inventory("user-123", "profile-1"),
                    _inventory("user-456", "profile-1"),
                ]
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(
                side_effect=lambda profile_pk, include_services, include_rules: (
                    _detail_payload(
                        profile_pk,
                        include_services=include_services,
                        include_rules=include_rules,
                    )
                )
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAUSE_PROFILE,
            {
                "config_entry_name": "Control D Home",
                ATTR_ENTITY_ID: [
                    entity_id
                    for entity_id in [
                        er.async_get(hass).async_get_entity_id(
                            "switch", DOMAIN, "user-456::profile::profile-1::paused"
                        )
                    ]
                    if entity_id is not None
                ],
                SERVICE_FIELD_MINUTES: 15,
            },
            blocking=True,
        )


async def test_pause_service_defaults_to_single_loaded_entry(hass) -> None:
    """The pause service should default to the only loaded entry when one exists."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_pause_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESUME_PROFILE,
        {},
        blocking=True,
    )

    assert runtime.client.async_set_profile_pause_until.await_count == 2


async def test_pause_service_requires_explicit_entry_when_multiple_loaded(hass) -> None:
    """The pause service should require explicit entry selection.

    This applies when multiple entries are loaded.
    """
    entry_one = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-one", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    entry_two = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-two", "entry_name": "Control D Cabin"},
        unique_id="user-456",
        title="Control D Cabin",
    )
    entry_one.add_to_hass(hass)
    entry_two.add_to_hass(hass)

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(
                side_effect=[
                    _inventory("user-123", "profile-1"),
                    _inventory("user-456", "profile-1"),
                ]
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(
                side_effect=lambda profile_pk, include_services, include_rules: (
                    _detail_payload(
                        profile_pk,
                        include_services=include_services,
                        include_rules=include_rules,
                    )
                )
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESUME_PROFILE,
            {},
            blocking=True,
        )


async def test_diagnostics_redact_entry_data_and_report_runtime_scope(hass) -> None:
    """Diagnostics should redact entry secrets and stay scoped to one runtime."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"][CONF_API_TOKEN] == "**REDACTED**"
    assert diagnostics["runtime"] == {
        "instance_id": "user-123",
        "profile_count": 2,
        "endpoint_count": 3,
        "discovered_endpoint_count": 2,
        "router_client_count": 1,
    }
