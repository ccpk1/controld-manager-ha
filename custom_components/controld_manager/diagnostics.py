"""Diagnostics support for Control D Manager."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ControlDManagerConfigEntry
from .const import CONF_API_TOKEN

TO_REDACT: set[str] = {"api_key", "token", "secret", CONF_API_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ControlDManagerConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    del hass
    runtime = entry.runtime_data
    if runtime is None:
        return {
            "entry": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "runtime": None,
        }

    registry = runtime.registry
    sync_status = runtime.sync_status

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "runtime": {
            "instance_id": runtime.instance_id,
            "refresh_intervals": {
                "configuration_sync_minutes": int(
                    runtime.refresh_intervals.configuration_sync.total_seconds() // 60
                ),
                "profile_analytics_minutes": int(
                    runtime.refresh_intervals.profile_analytics.total_seconds() // 60
                ),
                "endpoint_analytics_minutes": int(
                    runtime.refresh_intervals.endpoint_analytics.total_seconds() // 60
                ),
            },
            "sync_status": {
                "last_refresh_attempt": sync_status.last_refresh_attempt,
                "last_successful_refresh": sync_status.last_successful_refresh,
                "last_refresh_error": sync_status.last_refresh_error,
                "last_refresh_trigger": sync_status.last_refresh_trigger,
                "consecutive_failed_refreshes": (
                    sync_status.consecutive_failed_refreshes
                ),
                "refresh_in_progress": sync_status.refresh_in_progress,
            },
            "registry_summary": {
                "profile_count": len(registry.profiles),
                "endpoint_count": registry.endpoint_inventory.protected_endpoint_count,
                "discovered_endpoint_count": (
                    registry.endpoint_inventory.discovered_endpoint_count
                ),
                "router_client_count": registry.endpoint_inventory.router_client_count,
                "service_category_count": len(registry.service_categories),
                "filter_profile_count": len(registry.filters_by_profile),
                "service_profile_count": len(registry.services_by_profile),
                "rule_profile_count": len(registry.rules_by_profile),
                "option_profile_count": len(registry.options_by_profile),
            },
            "profiles": {
                profile_pk: {
                    "name": profile_row.name,
                    "managed_in_home_assistant": runtime.options.profile_policy(
                        profile_pk
                    ).managed_in_home_assistant,
                    "expose_external_filters": runtime.options.profile_policy(
                        profile_pk
                    ).expose_external_filters,
                    "advanced_profile_options": runtime.options.profile_policy(
                        profile_pk
                    ).advanced_profile_options,
                    "endpoint_sensors_enabled": runtime.options.profile_policy(
                        profile_pk
                    ).endpoint_sensors_enabled,
                    "endpoint_inactivity_threshold_minutes": (
                        runtime.options.profile_policy(
                            profile_pk
                        ).endpoint_inactivity_threshold_minutes
                    ),
                    "allowed_service_categories": sorted(
                        runtime.options.profile_policy(
                            profile_pk
                        ).allowed_service_categories
                    ),
                    "exposed_custom_rules": sorted(
                        runtime.options.profile_policy(profile_pk).exposed_custom_rules
                    ),
                    "filter_count": len(
                        registry.filters_by_profile.get(profile_pk, {})
                    ),
                    "service_count": len(
                        registry.services_by_profile.get(profile_pk, {})
                    ),
                    "rule_group_count": len(
                        registry.rule_groups_by_profile.get(profile_pk, {})
                    ),
                    "rule_count": len(registry.rules_by_profile.get(profile_pk, {})),
                    "option_count": len(
                        registry.options_by_profile.get(profile_pk, {})
                    ),
                    "endpoint_count": registry.protected_endpoint_count_for_profile(
                        profile_pk
                    ),
                }
                for profile_pk, profile_row in registry.profiles.items()
            },
        },
    }
