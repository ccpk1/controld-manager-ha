"""Entity and service tests for Control D Manager."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.components.select import ATTR_OPTION
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.api import (
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from custom_components.controld_manager.const import (
    ATTR_EXPIRED,
    ATTR_EXPIRES_AT,
    CONF_API_TOKEN,
    DOMAIN,
    SERVICE_CREATE_RULE,
    SERVICE_DELETE_RULE,
    SERVICE_DISABLE_PROFILE,
    SERVICE_ENABLE_PROFILE,
    SERVICE_FIELD_CANCEL_EXPIRATION,
    SERVICE_FIELD_CATALOG_TYPE,
    SERVICE_FIELD_COMMENT,
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
from custom_components.controld_manager.service_selectors import (
    _resolve_selected_option_pks,
    _resolve_selected_rule_group_pks,
    _resolve_selected_rule_identities,
    _resolve_selected_service_pks,
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
OPTION_CATALOG = [
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
        "PK": "safeyoutube",
        "title": "Restricted Youtube",
        "description": "Prevent Youtube from showing mature content.",
        "type": "toggle",
        "default_value": 0,
        "info_url": "https://docs.controld.com/docs/restricted-youtube",
    },
    {
        "PK": "block_rfc1918",
        "title": "DNS Rebind Protection",
        "description": "Blocks domains that point to RFC1918 addresses.",
        "type": "toggle",
        "default_value": 0,
        "info_url": "https://docs.controld.com/docs/dns-rebind-option",
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
            "7": "Custom",
            "9": "Branded",
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
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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
        {
            "PK": "adult_content",
            "name": "Adult Content",
            "levels": [
                {"title": "Relaxed", "name": "adult_relaxed", "status": 1},
                {"title": "Strict", "name": "adult_strict", "status": 0},
            ],
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
                "comment": "Here is my reason",
            },
        )
        if include_rules and profile_pk == "profile-1"
        else ()
    )
    return ControlDProfileDetailPayload(
        filters=filters,
        external_filters=(
            {
                "PK": "x-community",
                "name": "Community List",
                "action": {"do": 0, "status": 0},
                "status": 0,
            },
        ),
        options=(
            {"PK": "ai_malware", "value": 0.9},
            {"PK": "safesearch", "value": 1},
            {"PK": "block_rfc1918", "value": 1},
            {"PK": "ttl_blck", "value": 11},
        ),
        default_rule={"do": 1, "status": 1},
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
    adult_mode_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::filter_mode::adult_content"
    )
    default_rule_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::default_rule"
    )
    ai_malware_option_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::option::ai_malware"
    )
    safe_search_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::option::safesearch"
    )
    restricted_youtube_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::option::safeyoutube"
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
    assert adult_mode_entity_id is not None
    assert default_rule_entity_id is not None
    assert ai_malware_option_entity_id is not None
    assert safe_search_entity_id is not None
    assert restricted_youtube_entity_id is not None
    assert endpoint_status_entity_id is None
    assert service_entity_id is None
    assert hass.states.get(profile_count_entity_id).state == "2"
    assert hass.states.get(endpoint_count_entity_id).state == "3"
    assert hass.states.get(status_entity_id).state == "healthy"
    assert hass.states.get(status_entity_id).name == "Account Status"
    assert hass.states.get(endpoint_count_entity_id).name == "Account Endpoint count"
    assert hass.states.get(profile_count_entity_id).name == "Account Profile count"
    assert hass.states.get(sync_button_entity_id).name == "Account Sync now"
    assert hass.states.get(pause_switch_entity_id).name == "Primary Disable (Temporary)"
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
    assert hass.states.get(ads_mode_entity_id).state == "Relaxed"
    assert hass.states.get(default_rule_entity_id).state == "Bypassing"
    assert hass.states.get(ai_malware_option_entity_id).state == "Minimal"
    assert hass.states.get(safe_search_entity_id).state == "on"
    assert hass.states.get(restricted_youtube_entity_id).state == "off"
    adult_mode_entry = entity_registry.async_get(adult_mode_entity_id)
    assert adult_mode_entry is not None
    assert adult_mode_entry.disabled_by is not None


async def test_phase5_policy_enabled_entities_are_created_and_attached(hass) -> None:
    """Opted-in endpoint, service, and rule entities should be generated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    advanced_profile_options=True,
                    endpoint_sensors_enabled=True,
                    allowed_service_categories=frozenset({"audio"}),
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
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
        "select", DOMAIN, "user-123::profile::profile-1::service::amazonmusic"
    )
    advanced_toggle_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::option::block_rfc1918"
    )
    ttl_toggle_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::option::ttl_blck"
    )
    ecs_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::option::ecs_subnet"
    )
    advanced_select_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::option::b_resp"
    )
    rule_group_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::rule_group::1"
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
    assert advanced_toggle_entity_id is not None
    assert ttl_toggle_entity_id is not None
    assert ecs_entity_id is None
    assert advanced_select_entity_id is not None
    assert rule_group_entity_id is not None
    assert rule_entity_id is not None
    assert grouped_rule_entity_id is not None
    status_entry = entity_registry.async_get(status_entity_id)
    service_entry = entity_registry.async_get(service_entity_id)
    advanced_toggle_entry = entity_registry.async_get(advanced_toggle_entity_id)
    ttl_toggle_entry = entity_registry.async_get(ttl_toggle_entity_id)
    advanced_select_entry = entity_registry.async_get(advanced_select_entity_id)
    assert status_entry is not None
    assert service_entry is not None
    assert advanced_toggle_entry is not None
    assert ttl_toggle_entry is not None
    assert advanced_select_entry is not None
    assert profile_device is not None
    assert status_entry.device_id == profile_device.id
    assert service_entry.disabled_by is not None
    assert advanced_toggle_entry.disabled_by is not None
    assert ttl_toggle_entry.disabled_by is not None
    assert advanced_select_entry.disabled_by is not None
    assert hass.states.get(rule_group_entity_id).state == "bypass"
    assert (
        hass.states.get(rule_entity_id).name == "Primary Rules / Domain / example.com"
    )
    assert (
        hass.states.get(rule_entity_id).attributes["purpose"] == "purpose_profile_rule"
    )
    assert hass.states.get(rule_entity_id).attributes["action"] == "block"
    assert hass.states.get(rule_entity_id).attributes["comment"] == ""
    assert ATTR_EXPIRED not in hass.states.get(rule_entity_id).attributes
    assert ATTR_EXPIRES_AT not in hass.states.get(rule_entity_id).attributes
    assert hass.states.get(grouped_rule_entity_id).attributes["group"] == "Allow folder"
    assert hass.states.get(grouped_rule_entity_id).attributes["action"] == "bypass"
    assert (
        hass.states.get(grouped_rule_entity_id).attributes["comment"]
        == "Here is my reason"
    )


async def test_option_entities_expose_raw_purpose_attributes(hass) -> None:
    """Option entities should expose raw purpose translation keys."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    default_rule_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::default_rule"
    )
    ai_malware_option_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::option::ai_malware"
    )
    safe_search_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::option::safesearch"
    )
    rule_group_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::rule_group::1"
    )

    assert default_rule_entity_id is not None
    assert ai_malware_option_entity_id is not None
    assert safe_search_entity_id is not None
    assert rule_group_entity_id is None
    assert (
        hass.states.get(default_rule_entity_id).attributes["purpose"]
        == "purpose_profile_default_rule"
    )
    assert (
        hass.states.get(ai_malware_option_entity_id).attributes["purpose"]
        == "purpose_profile_option"
    )
    assert (
        hass.states.get(safe_search_entity_id).attributes["purpose"]
        == "purpose_profile_option"
    )


async def test_filter_and_service_selects_update_expected_modes(hass) -> None:
    """Mode-capable controls should expose and write the expected selected values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"}),
                    auto_enable_service_switches=True,
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    ads_mode_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::filter_mode::ads"
    )
    service_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::service::amazonmusic"
    )
    default_rule_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::default_rule"
    )
    rule_group_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::rule_group::1"
    )
    ai_malware_option_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::option::ai_malware"
    )
    runtime = entry.runtime_data

    assert ads_mode_entity_id is not None
    assert service_entity_id is not None
    assert default_rule_entity_id is not None
    assert rule_group_entity_id is None
    assert ai_malware_option_entity_id is not None
    assert hass.states.get(ads_mode_entity_id).state == "Relaxed"
    assert hass.states.get(service_entity_id).state == "Bypassed"
    assert hass.states.get(default_rule_entity_id).state == "Bypassing"
    assert hass.states.get(ai_malware_option_entity_id).state == "Minimal"

    with (
        patch.object(
            runtime.managers.profile,
            "async_set_filter_mode",
            new=AsyncMock(),
        ) as async_set_filter_mode,
        patch.object(
            runtime.managers.profile,
            "async_set_service_mode",
            new=AsyncMock(),
        ) as async_set_service_mode,
        patch.object(
            runtime.managers.profile,
            "async_set_default_rule_mode",
            new=AsyncMock(),
        ) as async_set_default_rule_mode,
        patch.object(
            runtime.managers.profile,
            "async_set_profile_option_select",
            new=AsyncMock(),
        ) as async_set_profile_option_select,
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                ATTR_ENTITY_ID: ads_mode_entity_id,
                ATTR_OPTION: "Balanced",
            },
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {
                ATTR_ENTITY_ID: default_rule_entity_id,
                ATTR_OPTION: "Redirecting",
            },
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {
                ATTR_ENTITY_ID: ai_malware_option_entity_id,
                ATTR_OPTION: "Aggressive",
            },
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {
                ATTR_ENTITY_ID: service_entity_id,
                ATTR_OPTION: "Blocked",
            },
            blocking=True,
        )

    async_set_filter_mode.assert_awaited_once_with("profile-1", "ads", "ads_medium")
    async_set_default_rule_mode.assert_awaited_once_with("profile-1", "Redirecting")
    async_set_profile_option_select.assert_awaited_once_with(
        "profile-1", "ai_malware", "Aggressive"
    )
    async_set_service_mode.assert_awaited_once_with(
        "profile-1", "amazonmusic", "Blocked"
    )


async def test_rule_group_select_updates_expected_mode(hass) -> None:
    """Folder rule controls should expose and write the expected selected values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {"group:1", "rule:group:1|example2.com"}
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    rule_group_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::rule_group::1"
    )
    grouped_rule_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::rule::group:1|example2.com"
    )
    runtime = entry.runtime_data

    assert rule_group_entity_id is not None
    assert grouped_rule_entity_id is not None
    assert hass.states.get(rule_group_entity_id).state == "bypass"

    with patch.object(
        runtime.managers.profile,
        "async_set_rule_group_mode",
        new=AsyncMock(),
    ) as async_set_rule_group_mode:
        await hass.services.async_call(
            "select",
            "select_option",
            {
                ATTR_ENTITY_ID: rule_group_entity_id,
                ATTR_OPTION: "block",
            },
            blocking=True,
        )

    async_set_rule_group_mode.assert_awaited_once_with("profile-1", "1", "block")


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
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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


async def test_removed_rule_entities_are_pruned_from_entity_registry(hass) -> None:
    """Removed rule entities should be deleted from the entity registry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "group:1",
                            "rule:root|example.com",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    rule_group_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::rule_group::1"
    )
    rule_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::rule::root|example.com"
    )
    grouped_rule_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::rule::group:1|example2.com"
    )

    assert rule_group_entity_id is not None
    assert rule_entity_id is not None
    assert grouped_rule_entity_id is not None

    entity_registry.async_update_entity(
        grouped_rule_entity_id,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    await hass.async_block_till_done()
    assert hass.states.get(grouped_rule_entity_id) is None

    runtime = entry.runtime_data

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=_inventory("user-123", "profile-1")),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(
                side_effect=lambda profile_pk, include_services, include_rules: replace(
                    _detail_payload(
                        profile_pk,
                        include_services=include_services,
                        include_rules=include_rules,
                    ),
                    groups=(),
                    rules=(),
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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

    assert entity_registry.async_get(rule_group_entity_id) is None
    assert entity_registry.async_get(rule_entity_id) is None
    assert entity_registry.async_get(grouped_rule_entity_id) is None


async def test_removed_dynamic_entities_are_pruned_across_platforms(hass) -> None:
    """Disabled and live dynamic entities should be removed when no longer desired."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    advanced_profile_options=True,
                    endpoint_sensors_enabled=True,
                    allowed_service_categories=frozenset({"audio"}),
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    endpoint_status_entity_id = entity_registry.async_get_entity_id(
        "binary_sensor", DOMAIN, "user-123::endpoint::device-1::status"
    )
    service_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::service::amazonmusic"
    )
    advanced_toggle_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::option::block_rfc1918"
    )
    advanced_select_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::option::b_resp"
    )
    social_filter_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::filter::social"
    )
    adult_mode_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::filter_mode::adult_content"
    )

    assert endpoint_status_entity_id is not None
    assert service_entity_id is not None
    assert advanced_toggle_entity_id is not None
    assert advanced_select_entity_id is not None
    assert social_filter_entity_id is not None
    assert adult_mode_entity_id is not None

    runtime = entry.runtime_data
    runtime.options = ControlDOptions(
        profile_policies={"profile-1": ControlDProfilePolicy()}
    )

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=_inventory("user-123", "profile-1")),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(
                side_effect=lambda profile_pk, include_services, include_rules: replace(
                    _detail_payload(
                        profile_pk,
                        include_services=include_services,
                        include_rules=include_rules,
                    ),
                    filters=tuple(
                        filter_payload
                        for filter_payload in _detail_payload(
                            profile_pk,
                            include_services=include_services,
                            include_rules=include_rules,
                        ).filters
                        if filter_payload["PK"] in {"ads", "ai_malware"}
                    ),
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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

    assert entity_registry.async_get(endpoint_status_entity_id) is None
    assert entity_registry.async_get(service_entity_id) is None
    assert entity_registry.async_get(advanced_toggle_entity_id) is None
    assert entity_registry.async_get(advanced_select_entity_id) is None
    assert entity_registry.async_get(social_filter_entity_id) is None
    assert entity_registry.async_get(adult_mode_entity_id) is None


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


async def test_disable_service_supports_profile_id_selector(hass) -> None:
    """The disable service should target the selected profile ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    profile_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert profile_device is not None

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISABLE_PROFILE,
        {SERVICE_FIELD_PROFILE_ID: [profile_device.id], SERVICE_FIELD_MINUTES: 30},
        blocking=True,
    )

    runtime.client.async_set_profile_disable_until.assert_awaited_once()
    profile_pk, disable_ttl = (
        runtime.client.async_set_profile_disable_until.await_args.args
    )
    assert profile_pk == "profile-1"
    assert isinstance(disable_ttl, int)


async def test_disable_service_supports_profile_names(hass) -> None:
    """The disable service should resolve selected profiles by profile name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISABLE_PROFILE,
        {SERVICE_FIELD_PROFILE_NAME: "Primary", SERVICE_FIELD_MINUTES: 45},
        blocking=True,
    )

    runtime.client.async_set_profile_disable_until.assert_awaited_once()
    assert (
        runtime.client.async_set_profile_disable_until.await_args.args[0] == "profile-1"
    )


async def test_disable_service_prefers_profile_ids_over_profile_names(hass) -> None:
    """The disable service should use selected profile IDs before names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    profile_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert profile_device is not None

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISABLE_PROFILE,
        {
            SERVICE_FIELD_PROFILE_ID: [profile_device.id],
            SERVICE_FIELD_PROFILE_NAME: "Secondary",
            SERVICE_FIELD_MINUTES: 15,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_disable_until.assert_awaited_once()
    profile_pk, disable_ttl = (
        runtime.client.async_set_profile_disable_until.await_args.args
    )
    assert profile_pk == "profile-1"
    assert isinstance(disable_ttl, int)


async def test_disable_service_rejects_account_device_target(hass) -> None:
    """The disable service should reject the Control D account device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    account_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123")}
    )
    assert account_device is not None

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_DISABLE_PROFILE,
            {SERVICE_FIELD_PROFILE_ID: [account_device.id], SERVICE_FIELD_MINUTES: 15},
            blocking=True,
        )


async def test_enable_service_supports_profile_id_selector(hass) -> None:
    """The enable service should target the selected profile ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    profile_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert profile_device is not None

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ENABLE_PROFILE,
        {SERVICE_FIELD_PROFILE_ID: [profile_device.id]},
        blocking=True,
    )

    runtime.client.async_set_profile_disable_until.assert_awaited_once_with(
        "profile-1", 0
    )


async def test_enable_service_prefers_config_entry_id_over_name(hass) -> None:
    """The enable service should use Integration ID before Integration name."""
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
        ),
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    entry_one.runtime_data.client.async_set_profile_disable_until = AsyncMock()
    entry_one.runtime_data.coordinator.async_refresh = AsyncMock()
    entry_two.runtime_data.client.async_set_profile_disable_until = AsyncMock()
    entry_two.runtime_data.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ENABLE_PROFILE,
        {
            "config_entry_id": entry_one.entry_id,
            "config_entry_name": "Control D Cabin",
            SERVICE_FIELD_PROFILE_NAME: "Primary",
        },
        blocking=True,
    )

    entry_one.runtime_data.client.async_set_profile_disable_until.assert_awaited_once_with(
        "profile-1", 0
    )
    entry_two.runtime_data.client.async_set_profile_disable_until.assert_not_awaited()


async def test_enable_service_supports_profile_names(hass) -> None:
    """The enable service should resolve selected profiles by profile name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ENABLE_PROFILE,
        {SERVICE_FIELD_PROFILE_NAME: "Primary"},
        blocking=True,
    )

    runtime.client.async_set_profile_disable_until.assert_awaited_once_with(
        "profile-1", 0
    )


async def test_enable_service_prefers_profile_ids_over_profile_names(hass) -> None:
    """The enable service should use selected profile IDs before profile names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    profile_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert profile_device is not None

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ENABLE_PROFILE,
        {
            SERVICE_FIELD_PROFILE_ID: [profile_device.id],
            SERVICE_FIELD_PROFILE_NAME: "Secondary",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_disable_until.assert_awaited_once_with(
        "profile-1", 0
    )


async def test_disable_service_prefers_config_entry_id_over_name(hass) -> None:
    """The disable service should use Integration ID before Integration name."""
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
        ),
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    target_profile = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert target_profile is not None

    entry_one.runtime_data.client.async_set_profile_disable_until = AsyncMock()
    entry_one.runtime_data.coordinator.async_refresh = AsyncMock()
    entry_two.runtime_data.client.async_set_profile_disable_until = AsyncMock()
    entry_two.runtime_data.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISABLE_PROFILE,
        {
            "config_entry_id": entry_one.entry_id,
            "config_entry_name": "Control D Cabin",
            SERVICE_FIELD_PROFILE_ID: [target_profile.id],
            SERVICE_FIELD_MINUTES: 20,
        },
        blocking=True,
    )

    entry_one.runtime_data.client.async_set_profile_disable_until.assert_awaited_once()
    entry_two.runtime_data.client.async_set_profile_disable_until.assert_not_awaited()


async def test_disable_service_rejects_mixed_instance_targets(hass) -> None:
    """The disable service should reject targets that span multiple instances."""
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
        ),
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    target_profile = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-456::profile::profile-1")}
    )
    assert target_profile is not None

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_DISABLE_PROFILE,
            {
                "config_entry_name": "Control D Home",
                SERVICE_FIELD_PROFILE_ID: [target_profile.id],
                SERVICE_FIELD_MINUTES: 15,
            },
            blocking=True,
        )


async def test_disable_service_requires_profile_selector(hass) -> None:
    """The disable service should require a profile ID or profile name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_DISABLE_PROFILE,
            {SERVICE_FIELD_MINUTES: 10},
            blocking=True,
        )


async def test_disable_service_rejects_entity_targets(hass) -> None:
    """The disable service should not accept generic entity targets."""
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

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_DISABLE_PROFILE,
            {ATTR_ENTITY_ID: [pause_switch_entity_id], SERVICE_FIELD_MINUTES: 30},
            blocking=True,
        )


async def test_enable_service_requires_profile_selector(hass) -> None:
    """The enable service should require a profile ID or profile name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_disable_until = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ENABLE_PROFILE,
            {},
            blocking=True,
        )


async def test_enable_service_rejects_entity_targets(hass) -> None:
    """The enable service should not accept generic entity targets."""
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

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ENABLE_PROFILE,
            {ATTR_ENTITY_ID: [pause_switch_entity_id]},
            blocking=True,
        )


async def test_enable_service_requires_explicit_entry(hass) -> None:
    """The enable service should require explicit entry selection.

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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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
            SERVICE_ENABLE_PROFILE,
            {},
            blocking=True,
        )


async def test_set_filter_state_supports_raw_filter_key(hass) -> None:
    """The filter service should resolve a raw Control D filter key."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_filter = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_FILTER_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: ["Primary", "Secondary"],
            SERVICE_FIELD_FILTER_ID: "ads",
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    assert runtime.client.async_set_profile_filter.await_count == 2
    assert all(
        call.args[1] == "ads"
        for call in runtime.client.async_set_profile_filter.await_args_list
    )


async def test_set_filter_state_supports_user_facing_names(hass) -> None:
    """The filter service should resolve one or more user-facing names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    profile_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert profile_device is not None

    runtime = entry.runtime_data
    runtime.client.async_set_profile_filter = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_FILTER_STATE,
        {
            SERVICE_FIELD_PROFILE_ID: [profile_device.id],
            SERVICE_FIELD_FILTER_NAME: ["ads & trackers", "Community List"],
            SERVICE_FIELD_ENABLED: True,
        },
        blocking=True,
    )

    assert runtime.client.async_set_profile_filter.await_count == 2
    assert {
        call.args[1] for call in runtime.client.async_set_profile_filter.await_args_list
    } == {"ads", "x-community"}


async def test_set_filter_state_prefers_filter_ids_over_names(hass) -> None:
    """The filter service should use raw filter IDs before names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_filter = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_FILTER_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_FILTER_ID: ["ads"],
            SERVICE_FIELD_FILTER_NAME: ["Community List"],
            SERVICE_FIELD_ENABLED: True,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_filter.assert_awaited_once()
    assert runtime.client.async_set_profile_filter.await_args.args[1] == "ads"


async def test_set_filter_state_prefers_config_entry_id_over_name(hass) -> None:
    """The filter service should use Integration ID before Integration name."""
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
        ),
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    entry_one.runtime_data.client.async_set_profile_filter = AsyncMock()
    entry_one.runtime_data.coordinator.async_refresh = AsyncMock()
    entry_two.runtime_data.client.async_set_profile_filter = AsyncMock()
    entry_two.runtime_data.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_FILTER_STATE,
        {
            "config_entry_id": entry_one.entry_id,
            "config_entry_name": "Control D Cabin",
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_FILTER_ID: ["ads"],
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    entry_one.runtime_data.client.async_set_profile_filter.assert_awaited_once()
    entry_two.runtime_data.client.async_set_profile_filter.assert_not_awaited()


async def test_set_filter_state_rejects_unknown_filter_name(hass) -> None:
    """The filter service should reject an unknown filter name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_FILTER_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_FILTER_NAME: "not-a-real-filter",
                SERVICE_FIELD_ENABLED: True,
            },
            blocking=True,
        )


async def test_set_filter_state_supports_external_filter_without_entity(hass) -> None:
    """The filter service should resolve external filters when entities stay hidden."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    assert (
        entity_registry.async_get_entity_id(
            "switch", DOMAIN, "user-123::profile::profile-1::filter::x-community"
        )
        is None
    )

    runtime = entry.runtime_data
    runtime.client.async_set_profile_filter = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_FILTER_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_FILTER_NAME: "Community List",
            SERVICE_FIELD_ENABLED: True,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_filter.assert_awaited_once()
    assert runtime.client.async_set_profile_filter.await_args.args[1] == "x-community"


async def test_set_filter_state_requires_profile_selector(hass) -> None:
    """The filter service should require a profile ID or profile name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_FILTER_STATE,
            {SERVICE_FIELD_FILTER_ID: ["ads"], SERVICE_FIELD_ENABLED: True},
            blocking=True,
        )


async def test_set_filter_state_requires_filter_selector(hass) -> None:
    """The filter service should require a filter ID or filter name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_FILTER_STATE,
            {SERVICE_FIELD_PROFILE_NAME: "Primary", SERVICE_FIELD_ENABLED: True},
            blocking=True,
        )


async def test_set_filter_state_rejects_entity_targets(hass) -> None:
    """The filter service should not accept generic entity targets."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    filter_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::filter::ads"
    )

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_FILTER_STATE,
            {
                ATTR_ENTITY_ID: [filter_entity_id],
                SERVICE_FIELD_FILTER_ID: ["ads"],
                SERVICE_FIELD_ENABLED: False,
            },
            blocking=True,
        )


async def test_set_service_state_supports_raw_service_key(hass) -> None:
    """The service-mode service should resolve a raw Control D service key."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_service = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_SERVICE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_SERVICE_ID: "amazonmusic",
            SERVICE_FIELD_MODE: "Blocked",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_service.assert_awaited_once_with(
        "profile-1",
        "amazonmusic",
        enabled=True,
        action_do=0,
    )


async def test_set_service_state_supports_live_lookup_without_enabled_categories(
    hass,
) -> None:
    """The service-mode service should still resolve live services.

    This should work even when no service categories are enabled for entities.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    assert runtime.registry.services_by_profile.get("profile-1", {}) == {}

    runtime.client.async_get_service_categories = AsyncMock(
        return_value=SERVICE_CATEGORIES
    )
    runtime.client.async_get_service_catalog = AsyncMock(return_value=SERVICE_CATALOG)
    runtime.client.async_get_profile_services = AsyncMock(
        return_value=[
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "category": "audio",
                "warning": "",
                "unlock_location": "JFK",
                "action": {"do": 1, "status": 1},
            }
        ]
    )
    runtime.client.async_set_profile_service = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_SERVICE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_SERVICE_NAME: "Amazon Music",
            SERVICE_FIELD_MODE: "Blocked",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_service.assert_awaited_once_with(
        "profile-1",
        "amazonmusic",
        enabled=True,
        action_do=0,
    )


async def test_set_service_state_supports_live_lookup_for_missing_loaded_category(
    hass,
) -> None:
    """The service-mode service should live-resolve filtered-out services."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    assert runtime.registry.services_by_profile.get("profile-1", {})
    assert "facebook" not in runtime.registry.services_by_profile["profile-1"]

    runtime.client.async_get_service_categories = AsyncMock(
        return_value=[
            {"PK": "audio", "name": "Audio", "count": 18},
            {"PK": "social", "name": "Social", "count": 10},
        ]
    )
    runtime.client.async_get_service_catalog = AsyncMock(
        return_value=[
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "category": "audio",
                "warning": "",
                "unlock_location": "JFK",
            },
            {
                "PK": "facebook",
                "name": "Facebook",
                "category": "social",
                "warning": "",
                "unlock_location": None,
            },
        ]
    )
    runtime.client.async_get_profile_services = AsyncMock(
        return_value=[
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "category": "audio",
                "warning": "",
                "unlock_location": "JFK",
                "action": {"do": 1, "status": 1},
            },
            {
                "PK": "facebook",
                "name": "Facebook",
                "category": "social",
                "warning": "",
                "unlock_location": None,
                "action": {"do": 1, "status": 1},
            },
        ]
    )
    runtime.client.async_set_profile_service = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_SERVICE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_SERVICE_ID: "facebook",
            SERVICE_FIELD_MODE: "Blocked",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_service.assert_awaited_once_with(
        "profile-1",
        "facebook",
        enabled=True,
        action_do=0,
    )


async def test_set_service_state_supports_user_facing_names(hass) -> None:
    """The service-mode service should resolve one or more user-facing names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    profile_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert profile_device is not None

    runtime = entry.runtime_data
    runtime.client.async_set_profile_service = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_SERVICE_STATE,
        {
            SERVICE_FIELD_PROFILE_ID: [profile_device.id],
            SERVICE_FIELD_SERVICE_NAME: ["amazon music"],
            SERVICE_FIELD_MODE: "Redirected",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_service.assert_awaited_once_with(
        "profile-1",
        "amazonmusic",
        enabled=True,
        action_do=2,
    )


async def test_set_service_state_prefers_service_ids_over_names(hass) -> None:
    """The service-mode service should use raw service IDs before names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_service = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_SERVICE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_SERVICE_ID: ["amazonmusic"],
            SERVICE_FIELD_SERVICE_NAME: ["not-a-real-service"],
            SERVICE_FIELD_MODE: "Off",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_service.assert_awaited_once_with(
        "profile-1",
        "amazonmusic",
        enabled=False,
        action_do=1,
    )


async def test_set_service_state_prefers_config_entry_id_over_name(hass) -> None:
    """The service-mode service should use Integration ID before name."""
    entry_one = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-one", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    entry_two = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-two", "entry_name": "Control D Cabin"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    entry_one.runtime_data.client.async_set_profile_service = AsyncMock()
    entry_one.runtime_data.coordinator.async_refresh = AsyncMock()
    entry_two.runtime_data.client.async_set_profile_service = AsyncMock()
    entry_two.runtime_data.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_SERVICE_STATE,
        {
            "config_entry_id": entry_one.entry_id,
            "config_entry_name": "Control D Cabin",
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_SERVICE_ID: ["amazonmusic"],
            SERVICE_FIELD_MODE: "Bypassed",
        },
        blocking=True,
    )

    entry_one.runtime_data.client.async_set_profile_service.assert_awaited_once()
    entry_two.runtime_data.client.async_set_profile_service.assert_not_awaited()


async def test_set_service_state_rejects_unknown_service_name(hass) -> None:
    """The service-mode service should reject an unknown service name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_get_service_categories = AsyncMock(
        return_value=SERVICE_CATEGORIES
    )
    runtime.client.async_get_service_catalog = AsyncMock(return_value=SERVICE_CATALOG)
    runtime.client.async_get_profile_services = AsyncMock(
        return_value=[
            {
                "PK": "amazonmusic",
                "name": "Amazon Music",
                "category": "audio",
                "warning": "",
                "unlock_location": "JFK",
                "action": {"do": 1, "status": 1},
            }
        ]
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SERVICE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_SERVICE_NAME: "not-a-real-service",
                SERVICE_FIELD_MODE: "Blocked",
            },
            blocking=True,
        )


async def test_set_service_state_surfaces_rejected_redirects_gracefully(hass) -> None:
    """The service-mode service should surface upstream mode rejections cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_service = AsyncMock(
        side_effect=ControlDApiResponseError("redirect not permitted")
    )
    runtime.coordinator.async_refresh = AsyncMock()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SERVICE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_SERVICE_ID: "amazonmusic",
                SERVICE_FIELD_MODE: "Redirected",
            },
            blocking=True,
        )


async def test_set_service_state_requires_profile_selector(hass) -> None:
    """The service-mode service should require a profile ID or profile name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SERVICE_STATE,
            {
                SERVICE_FIELD_SERVICE_ID: ["amazonmusic"],
                SERVICE_FIELD_MODE: "Blocked",
            },
            blocking=True,
        )


async def test_set_service_state_requires_service_selector(hass) -> None:
    """The service-mode service should require a service ID or service name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SERVICE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_MODE: "Blocked",
            },
            blocking=True,
        )


async def test_set_service_state_rejects_entity_targets(hass) -> None:
    """The service-mode service should not accept generic entity targets."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    service_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::service::amazonmusic"
    )

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SERVICE_STATE,
            {
                ATTR_ENTITY_ID: [service_entity_id],
                SERVICE_FIELD_SERVICE_ID: ["amazonmusic"],
                SERVICE_FIELD_MODE: "Blocked",
            },
            blocking=True,
        )


async def test_set_option_state_supports_toggle_option_id(hass) -> None:
    """The option service should resolve toggle options by raw Control D key."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: ["Primary", "Secondary"],
            SERVICE_FIELD_OPTION_ID: "safesearch",
            SERVICE_FIELD_ENABLED: True,
        },
        blocking=True,
    )

    assert runtime.client.async_set_profile_option.await_count == 2
    assert all(
        call.args[1] == "safesearch"
        and call.kwargs["enabled"] is True
        and call.kwargs["value"] is None
        for call in runtime.client.async_set_profile_option.await_args_list
    )


async def test_set_option_state_supports_select_option_name(hass) -> None:
    """The option service should resolve select options by user-facing title."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    profile_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "instance::user-123::profile::profile-1")}
    )
    assert profile_device is not None

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_ID: [profile_device.id],
            SERVICE_FIELD_OPTION_NAME: ["ai malware filter"],
            SERVICE_FIELD_VALUE: "Aggressive",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ai_malware",
        enabled=True,
        value="0.5",
    )


async def test_set_option_state_supports_turning_select_option_off(hass) -> None:
    """The option service should allow select-style options to be disabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "ai_malware",
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ai_malware",
        enabled=False,
        value=None,
    )


async def test_set_option_state_supports_select_option_default_enable(hass) -> None:
    """The option service should re-enable select options with a fallback value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()
    runtime.registry.options_by_profile["profile-1"]["ai_malware"] = replace(
        runtime.registry.options_by_profile["profile-1"]["ai_malware"],
        current_value_key=None,
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "ai_malware",
            SERVICE_FIELD_ENABLED: True,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ai_malware",
        enabled=True,
        value="0.9",
    )


async def test_set_option_state_supports_ecs_subnet_value(hass) -> None:
    """The option service should support the proven ECS select values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "ecs_subnet",
            SERVICE_FIELD_VALUE: "Auto",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ecs_subnet",
        enabled=True,
        value="1",
    )


async def test_set_option_state_supports_proven_block_response_value(hass) -> None:
    """The option service should support the proven block response values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "b_resp",
            SERVICE_FIELD_VALUE: "NXDOMAIN",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "b_resp",
        enabled=True,
        value="3",
    )


async def test_set_option_state_supports_raw_block_response_value(hass) -> None:
    """The option service should also accept raw upstream select values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "b_resp",
            SERVICE_FIELD_VALUE: "5",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "b_resp",
        enabled=True,
        value="5",
    )


async def test_set_option_state_supports_raw_ecs_subnet_value(hass) -> None:
    """The option service should accept raw upstream ECS values too."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "ecs_subnet",
            SERVICE_FIELD_VALUE: "1",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ecs_subnet",
        enabled=True,
        value="1",
    )


async def test_set_option_state_supports_turning_ecs_subnet_off(hass) -> None:
    """The option service should allow ECS subnet to be disabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "ecs_subnet",
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ecs_subnet",
        enabled=False,
        value=None,
    )


async def test_set_option_state_rejects_unimplemented_block_response_values(
    hass,
) -> None:
    """The option service should reject unresolved block response branches."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_OPTION_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_OPTION_ID: "b_resp",
                SERVICE_FIELD_VALUE: "Custom",
            },
            blocking=True,
        )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_OPTION_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_OPTION_ID: "b_resp",
                SERVICE_FIELD_VALUE: "Branded",
            },
            blocking=True,
        )


async def test_set_option_state_rejects_unproven_ecs_subnet_value(hass) -> None:
    """The option service should reject the unresolved ECS Custom value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_OPTION_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_OPTION_ID: "ecs_subnet",
                SERVICE_FIELD_VALUE: "Custom",
            },
            blocking=True,
        )


async def test_set_option_state_supports_numeric_field_value(hass) -> None:
    """The option service should allow explicit numeric values for TTL fields."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: "ttl_blck",
            SERVICE_FIELD_VALUE: 20,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "ttl_blck",
        enabled=True,
        value="20",
    )


@pytest.mark.parametrize(
    ("option_id", "seconds"),
    (("ttl_spff", 25), ("ttl_pass", 600)),
)
async def test_set_option_state_supports_other_numeric_ttl_fields(
    hass, option_id: str, seconds: int
) -> None:
    """The option service should support the other numeric TTL fields."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: option_id,
            SERVICE_FIELD_VALUE: seconds,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        option_id,
        enabled=True,
        value=str(seconds),
    )


async def test_set_option_state_rejects_numeric_field_value_when_disabled(hass) -> None:
    """The option service should reject conflicting disable plus value writes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_OPTION_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_OPTION_ID: "ttl_spff",
                SERVICE_FIELD_ENABLED: False,
                SERVICE_FIELD_VALUE: 20,
            },
            blocking=True,
        )


async def test_set_option_state_prefers_option_ids_over_names(hass) -> None:
    """The option service should use raw option IDs before names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_option = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_OPTION_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_OPTION_ID: ["safesearch"],
            SERVICE_FIELD_OPTION_NAME: ["not-a-real-option"],
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_option.assert_awaited_once_with(
        "profile-1",
        "safesearch",
        enabled=False,
        value=None,
    )


async def test_set_option_state_requires_mutation_field(hass) -> None:
    """The option service should require Enabled or Value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_OPTION_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_OPTION_ID: ["safesearch"],
            },
            blocking=True,
        )


async def test_set_option_state_rejects_unknown_option_name(hass) -> None:
    """The option service should reject an unknown option title."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_OPTION_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_OPTION_NAME: "not-a-real-option",
                SERVICE_FIELD_ENABLED: True,
            },
            blocking=True,
        )


async def test_set_default_rule_state_updates_targeted_profiles(hass) -> None:
    """The default-rule service should bulk update the selected profiles."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_default_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_DEFAULT_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: ["Primary", "Secondary"],
            SERVICE_FIELD_MODE: "Redirecting",
        },
        blocking=True,
    )

    assert runtime.client.async_set_profile_default_rule.await_count == 2
    assert all(
        call.kwargs["action_do"] == 3 and call.kwargs["via"] == "LOCAL"
        for call in runtime.client.async_set_profile_default_rule.await_args_list
    )


async def test_set_default_rule_state_prefers_config_entry_id_over_name(hass) -> None:
    """The default-rule service should use config_entry_id before entry name."""
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    entry_one.runtime_data.client.async_set_profile_default_rule = AsyncMock()
    entry_one.runtime_data.coordinator.async_refresh = AsyncMock()
    entry_two.runtime_data.client.async_set_profile_default_rule = AsyncMock()
    entry_two.runtime_data.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_DEFAULT_RULE_STATE,
        {
            "config_entry_id": entry_one.entry_id,
            "config_entry_name": "Control D Cabin",
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_MODE: "Blocking",
        },
        blocking=True,
    )

    entry_one.runtime_data.client.async_set_profile_default_rule.assert_awaited_once()
    entry_two.runtime_data.client.async_set_profile_default_rule.assert_not_awaited()


async def test_set_rule_state_supports_raw_rule_identity(hass) -> None:
    """The rule service should resolve and update one rule by raw identity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["group:1|example2.com"],
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_rule.assert_awaited_once_with(
        "profile-1",
        "example2.com",
        enabled=False,
        action_do=1,
        group_pk="1",
        ttl=None,
        comment="Here is my reason",
    )


async def test_create_rule_supports_default_root_rule_creation(hass) -> None:
    """The create-rule service should default to an enabled blocking root rule."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_create_profile_rules = AsyncMock()
    runtime.client.async_get_profile_detail = AsyncMock(
        return_value=_detail_payload(
            "profile-1",
            include_services=False,
            include_rules=True,
        )
    )
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CREATE_RULE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_HOSTNAME: ["new.example"],
        },
        blocking=True,
    )

    runtime.client.async_create_profile_rules.assert_awaited_once_with(
        "profile-1",
        ["new.example"],
        enabled=True,
        action_do=0,
        group_pk=None,
        comment="",
        ttl=None,
    )
    assert (
        runtime.registry.rules_by_profile["profile-1"]["root|new.example"].rule_pk
        == "new.example"
    )


async def test_create_rule_supports_grouped_rich_creation(hass) -> None:
    """The create-rule service should support grouped creates with rich fields."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_create_profile_rules = AsyncMock()
    runtime.client.async_get_profile_detail = AsyncMock(
        return_value=_detail_payload(
            "profile-1",
            include_services=False,
            include_rules=True,
        )
    )
    runtime.coordinator.async_refresh = AsyncMock()
    expire_at = datetime(2026, 4, 7, 18, 30, tzinfo=UTC)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CREATE_RULE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_HOSTNAME: ["new2.example"],
            SERVICE_FIELD_RULE_GROUP_NAME: "Allow folder",
            SERVICE_FIELD_MODE: "redirect",
            SERVICE_FIELD_COMMENT: "Temporary redirect",
            SERVICE_FIELD_EXPIRE_AT: expire_at,
        },
        blocking=True,
    )

    runtime.client.async_create_profile_rules.assert_awaited_once_with(
        "profile-1",
        ["new2.example"],
        enabled=True,
        action_do=2,
        group_pk="1",
        comment="Temporary redirect",
        ttl=int(expire_at.timestamp()),
    )
    created_rule = runtime.registry.rules_by_profile["profile-1"][
        "group:1|new2.example"
    ]
    assert created_rule.group_name == "Allow folder"
    assert created_rule.action_do == 2


async def test_create_rule_rejects_existing_hostname(hass) -> None:
    """The create-rule service should reject existing hostnames up front."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entry.runtime_data.client.async_get_profile_detail = AsyncMock(
        return_value=_detail_payload(
            "profile-1",
            include_services=False,
            include_rules=True,
        )
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CREATE_RULE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_HOSTNAME: ["example.com"],
            },
            blocking=True,
        )


async def test_delete_rule_deletes_targeted_rules(hass) -> None:
    """The delete-rule service should delete rules resolved by identity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_delete_profile_rules = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_DELETE_RULE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["group:1|example2.com"],
        },
        blocking=True,
    )

    runtime.client.async_delete_profile_rules.assert_awaited_once_with(
        "profile-1",
        ["example2.com"],
    )
    assert "group:1|example2.com" not in runtime.registry.rules_by_profile["profile-1"]


async def test_set_rule_state_supports_mode_updates(hass) -> None:
    """The rule service should allow mode updates without changing enabled state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["root|example.com"],
            SERVICE_FIELD_MODE: "redirect",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_rule.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=2,
        group_pk=None,
        ttl=None,
        comment="",
    )


async def test_set_rule_state_supports_bare_hostname(hass) -> None:
    """The rule service should accept a bare hostname when it is unambiguous."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["example.com"],
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    runtime.client.async_set_profile_rule.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=False,
        action_do=0,
        group_pk=None,
        ttl=None,
        comment="",
    )


async def test_set_rule_state_supports_enabled_and_mode_together(hass) -> None:
    """The rule service should allow toggling and mode changes in one call."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["group:1|example2.com"],
            SERVICE_FIELD_ENABLED: False,
            SERVICE_FIELD_MODE: "block",
        },
        blocking=True,
    )

    runtime.client.async_set_profile_rule.assert_awaited_once_with(
        "profile-1",
        "example2.com",
        enabled=False,
        action_do=0,
        group_pk="1",
        ttl=None,
        comment="Here is my reason",
    )


async def test_set_rule_state_supports_comment_updates(hass) -> None:
    """The rule service should allow comment-only updates without other mutations."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_update_profile_rule_rich = AsyncMock()
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["root|example.com"],
            SERVICE_FIELD_COMMENT: "Temporary allowance",
        },
        blocking=True,
    )

    runtime.client.async_update_profile_rule_rich.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=0,
        group_pk=None,
        ttl=None,
        comment="Temporary allowance",
    )
    runtime.client.async_set_profile_rule.assert_not_awaited()


async def test_set_rule_state_supports_duration_updates(hass) -> None:
    """The rule service should convert a duration into a future expiration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_update_profile_rule_rich = AsyncMock()
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    frozen_now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    with patch(
        "custom_components.controld_manager.services.dt_util.utcnow",
        return_value=frozen_now,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_RULE_IDENTITY: ["root|example.com"],
                SERVICE_FIELD_EXPIRATION_DURATION: timedelta(minutes=30),
            },
            blocking=True,
        )

    runtime.client.async_update_profile_rule_rich.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=0,
        group_pk=None,
        ttl=int((frozen_now + timedelta(minutes=30)).timestamp()),
        comment="",
    )
    runtime.client.async_set_profile_rule.assert_not_awaited()


async def test_set_rule_state_expire_at_overrides_duration(hass) -> None:
    """The rule service should prefer expire_at over expiration_duration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_update_profile_rule_rich = AsyncMock()
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    frozen_now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    expire_at = datetime(2026, 4, 8, 9, 15, tzinfo=UTC)
    with patch(
        "custom_components.controld_manager.services.dt_util.utcnow",
        return_value=frozen_now,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_RULE_IDENTITY: ["root|example.com"],
                SERVICE_FIELD_EXPIRATION_DURATION: timedelta(minutes=30),
                SERVICE_FIELD_EXPIRE_AT: expire_at,
            },
            blocking=True,
        )

    runtime.client.async_update_profile_rule_rich.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=0,
        group_pk=None,
        ttl=int(expire_at.timestamp()),
        comment="",
    )
    runtime.client.async_set_profile_rule.assert_not_awaited()


async def test_set_rule_state_cancel_expiration_uses_rich_update(hass) -> None:
    """The rule service should cancel expiration using the rich rule update."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_update_profile_rule_rich = AsyncMock()
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["root|example.com"],
            SERVICE_FIELD_CANCEL_EXPIRATION: True,
        },
        blocking=True,
    )

    runtime.client.async_update_profile_rule_rich.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=0,
        group_pk=None,
        ttl=-1,
        comment="",
    )
    runtime.client.async_set_profile_rule.assert_not_awaited()


async def test_set_rule_state_cancel_expiration_overrides_expire_inputs(hass) -> None:
    """The rule service should ignore expiration inputs when canceling."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_update_profile_rule_rich = AsyncMock()
    runtime.client.async_set_profile_rule = AsyncMock()
    runtime.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["root|example.com"],
            SERVICE_FIELD_CANCEL_EXPIRATION: True,
            SERVICE_FIELD_EXPIRATION_DURATION: timedelta(minutes=30),
            SERVICE_FIELD_EXPIRE_AT: datetime(2026, 4, 8, 9, 15, tzinfo=UTC),
        },
        blocking=True,
    )

    runtime.client.async_update_profile_rule_rich.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=0,
        group_pk=None,
        ttl=-1,
        comment="",
    )
    runtime.client.async_set_profile_rule.assert_not_awaited()


async def test_rule_entity_exposes_expiration_attributes(hass) -> None:
    """Rule entities should expose the current expiration timestamp and state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset({"rule:root|example.com"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    entry.add_to_hass(hass)

    expired_ttl = int(datetime(2026, 4, 6, 12, 0, tzinfo=UTC).timestamp())

    def _expired_detail(
        profile_pk: str, *, include_services: bool, include_rules: bool
    ) -> ControlDProfileDetailPayload:
        del include_services
        if not include_rules or profile_pk != "profile-1":
            return _detail_payload(
                profile_pk,
                include_services=False,
                include_rules=False,
            )
        return ControlDProfileDetailPayload(
            filters=_detail_payload(
                profile_pk, include_services=False, include_rules=False
            ).filters,
            external_filters=(
                {
                    "PK": "x-community",
                    "name": "Community List",
                    "action": {"do": 0, "status": 0},
                    "status": 0,
                },
            ),
            options=(
                {"PK": "ai_malware", "value": 0.9},
                {"PK": "safesearch", "value": 1},
                {"PK": "block_rfc1918", "value": 1},
                {"PK": "ttl_blck", "value": 11},
            ),
            default_rule={"do": 1, "status": 1},
            services=(),
            groups=(),
            rules=(
                {
                    "PK": "example.com",
                    "order": 1,
                    "group": 0,
                    "action": {"do": 0, "status": 0, "ttl": expired_ttl},
                    "comment": "expired rule",
                },
            ),
        )

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_inventory",
            new=AsyncMock(return_value=_inventory("user-123", "profile-1")),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_detail",
            new=AsyncMock(side_effect=_expired_detail),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=SERVICE_CATEGORIES),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=SERVICE_CATALOG),
        ),
        patch(
            "custom_components.controld_manager.switch.dt_util.utcnow",
            return_value=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    rule_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::rule::root|example.com"
    )
    state = hass.states.get(rule_entity_id)
    assert state is not None
    assert state.state == "off"
    assert state.attributes[ATTR_EXPIRED] is True
    assert (
        state.attributes[ATTR_EXPIRES_AT]
        == datetime.fromtimestamp(expired_ttl, UTC).isoformat()
    )


async def test_set_rule_state_prefers_config_entry_id_over_name(hass) -> None:
    """The rule service should use config_entry_id when both entry selectors exist."""
    entry_one = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    entry_two = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "other-token", "entry_name": "Control D Cabin"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    entry_one.runtime_data.client.async_set_profile_rule = AsyncMock()
    entry_one.runtime_data.coordinator.async_refresh = AsyncMock()
    entry_two.runtime_data.client.async_set_profile_rule = AsyncMock()
    entry_two.runtime_data.coordinator.async_refresh = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RULE_STATE,
        {
            "config_entry_id": entry_one.entry_id,
            "config_entry_name": "Control D Cabin",
            SERVICE_FIELD_PROFILE_NAME: "Primary",
            SERVICE_FIELD_RULE_IDENTITY: ["group:1|example2.com"],
            SERVICE_FIELD_ENABLED: False,
        },
        blocking=True,
    )

    entry_one.runtime_data.client.async_set_profile_rule.assert_awaited_once()
    entry_two.runtime_data.client.async_set_profile_rule.assert_not_awaited()


async def test_set_rule_state_requires_mutation_field(hass) -> None:
    """The rule service should require at least one mutation field."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_RULE_IDENTITY: "root|example.com",
            },
            blocking=True,
        )


async def test_set_rule_state_requires_profile_selector(hass) -> None:
    """The rule service should require a profile ID or profile name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            {
                SERVICE_FIELD_RULE_IDENTITY: ["group:1|example2.com"],
                SERVICE_FIELD_ENABLED: False,
            },
            blocking=True,
        )


async def test_set_rule_state_requires_rule_selector(hass) -> None:
    """The rule service should require a rule identity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_ENABLED: False,
            },
            blocking=True,
        )


async def test_set_rule_state_rejects_entity_targets(hass) -> None:
    """The rule service should not accept generic entity targets."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    rule_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::rule::group:1|example2.com"
    )

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            {
                ATTR_ENTITY_ID: [rule_entity_id],
                SERVICE_FIELD_RULE_IDENTITY: ["group:1|example2.com"],
                SERVICE_FIELD_ENABLED: False,
            },
            blocking=True,
        )


async def test_set_rule_state_surfaces_upstream_failures(hass) -> None:
    """The rule service should surface upstream write failures cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "rule:root|example.com",
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    runtime = entry.runtime_data
    runtime.client.async_set_profile_rule = AsyncMock(
        side_effect=ControlDApiResponseError("rule update rejected")
    )
    runtime.coordinator.async_refresh = AsyncMock()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RULE_STATE,
            {
                SERVICE_FIELD_PROFILE_NAME: "Primary",
                SERVICE_FIELD_RULE_IDENTITY: "group:1|example2.com",
                SERVICE_FIELD_ENABLED: False,
            },
            blocking=True,
        )


async def test_selector_layer_resolves_services_by_id_and_name(hass) -> None:
    """The selector layer should resolve services by raw ID or display name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    allowed_service_categories=frozenset({"audio"})
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    assert _resolve_selected_service_pks(
        entry,
        frozenset({"profile-1"}),
        requested_service_ids=["amazonmusic"],
        requested_service_names=["does not matter"],
    ) == {"profile-1": frozenset({"amazonmusic"})}

    assert _resolve_selected_service_pks(
        entry,
        frozenset({"profile-1"}),
        requested_service_ids=[],
        requested_service_names=["Amazon Music"],
    ) == {"profile-1": frozenset({"amazonmusic"})}


async def test_selector_layer_resolves_rule_groups_by_name(hass) -> None:
    """The selector layer should resolve rule groups by raw ID or display name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    assert _resolve_selected_rule_group_pks(
        entry,
        frozenset({"profile-1"}),
        requested_group_ids=[],
        requested_group_names=["Allow folder"],
    ) == {"profile-1": frozenset({"1"})}


async def test_selector_layer_resolves_rules_by_identity(hass) -> None:
    """The selector layer should resolve rules by identity or bare hostname."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options=ControlDOptions(
            profile_policies={
                "profile-1": ControlDProfilePolicy(
                    exposed_custom_rules=frozenset(
                        {
                            "group:1",
                            "rule:group:1|example2.com",
                        }
                    )
                )
            }
        ).as_mapping(),
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    assert _resolve_selected_rule_identities(
        entry,
        frozenset({"profile-1"}),
        requested_rule_identities=["group:1|example2.com"],
    ) == {"profile-1": frozenset({"group:1|example2.com"})}

    assert _resolve_selected_rule_identities(
        entry,
        frozenset({"profile-1"}),
        requested_rule_identities=["example2.com"],
    ) == {"profile-1": frozenset({"group:1|example2.com"})}


async def test_selector_layer_resolves_profile_options_by_id_and_title(hass) -> None:
    """The selector layer should resolve profile options by ID or title."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    assert _resolve_selected_option_pks(
        entry,
        frozenset({"profile-1"}),
        requested_option_ids=["ai_malware"],
        requested_option_titles=["ignored"],
    ) == {"profile-1": frozenset({"ai_malware"})}

    assert _resolve_selected_option_pks(
        entry,
        frozenset({"profile-1"}),
        requested_option_ids=[],
        requested_option_titles=["AI Malware Filter"],
    ) == {"profile-1": frozenset({"ai_malware"})}


async def test_get_catalog_returns_filters(hass) -> None:
    """The catalog service should return native filters before 3rd-party filters."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_CATALOG,
        {SERVICE_FIELD_CATALOG_TYPE: "filters", SERVICE_FIELD_PROFILE_NAME: "Primary"},
        blocking=True,
        return_response=True,
    )

    assert response["catalog_type"] == "filters"
    items = response["items"]
    assert items[0]["filter_id"] == "ads"
    assert items[0]["external"] is False
    assert items[-1]["filter_id"] == "x-community"
    assert items[-1]["external"] is True
    assert "ads, Ads & Trackers" in response["text"]
    assert "x-community, Community List" in response["text"]


async def test_get_catalog_returns_services(hass) -> None:
    """The catalog service should return service rows for the selected scope."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_categories",
            new=AsyncMock(return_value=SERVICE_CATEGORIES),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_service_catalog",
            new=AsyncMock(return_value=SERVICE_CATALOG),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_services",
            new=AsyncMock(
                side_effect=lambda profile_pk: (
                    _detail_payload(
                        profile_pk,
                        include_services=True,
                        include_rules=False,
                    ).services
                )
            ),
        ),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_CATALOG,
            {
                SERVICE_FIELD_CATALOG_TYPE: "services",
                SERVICE_FIELD_PROFILE_NAME: "Primary",
            },
            blocking=True,
            return_response=True,
        )

    assert response["catalog_type"] == "services"
    assert response["items"][0]["service_id"] == "amazonmusic"
    assert response["items"][0]["category_name"] == "Audio"
    assert "amazonmusic, Amazon Music, Audio" in response["text"]


async def test_get_catalog_returns_rules(hass) -> None:
    """The catalog service should return both groups and rules."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    with (
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_groups",
            new=AsyncMock(
                side_effect=lambda profile_pk: (
                    _detail_payload(
                        profile_pk,
                        include_services=False,
                        include_rules=True,
                    ).groups
                )
            ),
        ),
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_rules",
            new=AsyncMock(
                side_effect=lambda profile_pk: (
                    _detail_payload(
                        profile_pk,
                        include_services=False,
                        include_rules=True,
                    ).rules
                )
            ),
        ),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_CATALOG,
            {
                SERVICE_FIELD_CATALOG_TYPE: "rules",
                SERVICE_FIELD_PROFILE_NAME: "Primary",
            },
            blocking=True,
            return_response=True,
        )

    assert response["catalog_type"] == "rules"
    assert any(item["item_type"] == "group" for item in response["items"])
    assert any(item["item_type"] == "rule" for item in response["items"])


async def test_get_catalog_returns_profile_options(hass) -> None:
    """The catalog service should return normalized profile options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_CATALOG,
        {
            SERVICE_FIELD_CATALOG_TYPE: "profile_options",
            SERVICE_FIELD_PROFILE_NAME: "Primary",
        },
        blocking=True,
        return_response=True,
    )

    assert response["catalog_type"] == "profile_options"
    assert any(item["option_id"] == "ai_malware" for item in response["items"])
    assert any(
        "ai_malware, AI Malware Filter" in line
        for line in response["text"].splitlines()
    )


async def test_get_catalog_defaults_to_all_profiles_in_single_entry(hass) -> None:
    """The catalog service should return all managed profiles for one entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_CATALOG,
        {SERVICE_FIELD_CATALOG_TYPE: "filters"},
        blocking=True,
        return_response=True,
    )

    assert len(response["profiles"]) == 2


async def test_get_catalog_requires_explicit_entry_when_multiple_loaded(hass) -> None:
    """The catalog service should require entry disambiguation when needed."""
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
        patch(
            "custom_components.controld_manager.api.client.ControlDAPIClient.async_get_profile_option_catalog",
            new=AsyncMock(return_value=OPTION_CATALOG),
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
        assert await hass.config_entries.async_setup(entry_one.entry_id)
        await hass.async_block_till_done()
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id)
            await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_CATALOG,
            {SERVICE_FIELD_CATALOG_TYPE: "filters"},
            blocking=True,
            return_response=True,
        )


async def test_external_filter_entities_are_disabled_by_default_when_exposed(
    hass,
) -> None:
    """External filter entities should be created disabled-by-default when opted in."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "token-value", "entry_name": "Control D Home"},
        options={
            "profile_policies": {
                "profile-1": {"expose_external_filters": True},
                "profile-2": {"expose_external_filters": True},
            }
        },
        unique_id="user-123",
        title="Control D Home",
    )
    await _async_setup_entry(hass, entry, _inventory("user-123", "profile-1"))

    entity_registry = er.async_get(hass)
    switch_entity_id = entity_registry.async_get_entity_id(
        "switch", DOMAIN, "user-123::profile::profile-1::filter::x-community"
    )
    select_entity_id = entity_registry.async_get_entity_id(
        "select", DOMAIN, "user-123::profile::profile-1::filter_mode::x-community"
    )
    switch_entry = (
        entity_registry.async_get(switch_entity_id)
        if switch_entity_id is not None
        else None
    )
    select_entry = (
        entity_registry.async_get(select_entity_id)
        if select_entity_id is not None
        else None
    )

    assert switch_entry is not None
    assert switch_entry.disabled_by is not None
    assert select_entry is None


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
