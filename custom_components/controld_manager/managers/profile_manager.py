"""Profile normalization and orchestration for Control D."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..models import (
    ControlDFilter,
    ControlDProfileSummary,
    default_rule_action_from_mode,
    rule_group_action_from_mode,
)
from .base_manager import BaseManager


class ProfileManager(BaseManager):
    """Own profile normalization and profile-scoped business logic."""

    def normalize_profiles(
        self, profiles_payload: tuple[dict[str, Any], ...]
    ) -> dict[str, ControlDProfileSummary]:
        """Normalize profile inventory into immutable profile summaries."""
        profiles: dict[str, ControlDProfileSummary] = {}
        for profile_payload in profiles_payload:
            profile_pk = self._require_string(profile_payload, "PK")
            name = self._require_string(profile_payload, "name")
            profiles[profile_pk] = ControlDProfileSummary(
                profile_pk=profile_pk,
                name=name,
                paused_until=self._normalize_paused_until(profile_payload),
            )
        return profiles

    def _normalize_paused_until(
        self, profile_payload: dict[str, Any]
    ) -> datetime | None:
        """Normalize known read variants into one paused-until field."""
        for key in ("disable_ttl", "disable"):
            normalized_value = self._normalize_datetime_value(profile_payload.get(key))
            if normalized_value is not None:
                return normalized_value
        return None

    def _normalize_datetime_value(self, value: Any) -> datetime | None:
        """Normalize a supported API date or epoch value into UTC."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value, UTC)
        if isinstance(value, str) and value:
            if value.isdigit():
                return datetime.fromtimestamp(int(value), UTC)
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                    UTC
                )
            except ValueError:
                return None
        return None

    async def async_disable_profiles(self, profile_pks: set[str], minutes: int) -> None:
        """Disable one or more profiles until a future timestamp."""
        paused_until = dt_util.utcnow() + timedelta(minutes=minutes)
        disable_ttl = int(paused_until.timestamp())
        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_disable_until(
                    profile_pk, disable_ttl
                )
                for profile_pk in profile_pks
            )
        )
        await self.runtime.active_coordinator.async_refresh()

    async def async_enable_profiles(self, profile_pks: set[str]) -> None:
        """Enable one or more disabled profiles immediately."""
        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_disable_until(profile_pk, 0)
                for profile_pk in profile_pks
            )
        )
        await self.runtime.active_coordinator.async_refresh()

    async def async_set_filter_enabled(
        self, profile_pk: str, filter_pk: str, enabled: bool
    ) -> None:
        """Enable or disable one profile filter."""
        await self.async_set_filters_enabled({profile_pk: filter_pk}, enabled)

    async def async_set_filters_enabled(
        self, profile_filters: dict[str, str], enabled: bool
    ) -> None:
        """Enable or disable one filter across one or more targeted profiles."""
        updated_filters: list[tuple[str, str, ControlDFilter]] = []
        for profile_pk, filter_pk in profile_filters.items():
            filter_row = self.runtime.registry.filters_by_profile[profile_pk][filter_pk]
            updated_filters.append((profile_pk, filter_pk, filter_row))

        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_filter(
                    profile_pk,
                    filter_pk,
                    enabled=enabled,
                    action_do=(1 if not enabled else filter_row.action_do),
                    level_slug=(filter_row.effective_level_slug if enabled else None),
                )
                for profile_pk, filter_pk, filter_row in updated_filters
            )
        )

        for profile_pk, filter_pk, filter_row in updated_filters:
            self.runtime.registry.filters_by_profile[profile_pk][filter_pk] = replace(
                filter_row,
                enabled=enabled,
                selected_level_slug=filter_row.effective_level_slug,
            )

        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    async def async_set_filter_mode(
        self, profile_pk: str, filter_pk: str, level_slug: str
    ) -> None:
        """Set the selected mode for one filter."""
        filter_row = self.runtime.registry.filters_by_profile[profile_pk][filter_pk]
        await self.runtime.client.async_set_profile_filter(
            profile_pk,
            filter_pk,
            enabled=True,
            action_do=filter_row.action_do,
            level_slug=level_slug,
        )
        self.runtime.registry.filters_by_profile[profile_pk][filter_pk] = replace(
            filter_row,
            enabled=True,
            selected_level_slug=level_slug,
        )
        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    async def async_set_service_mode(
        self, profile_pk: str, service_pk: str, mode: str
    ) -> None:
        """Set the selected mode for one service rule."""
        service_row = self.runtime.registry.services_by_profile[profile_pk][service_pk]
        enabled = mode != "Off"
        action_do = service_row.action_do
        if mode == "Blocked":
            action_do = 0
        elif mode == "Bypassed":
            action_do = 1
        elif mode == "Redirected":
            action_do = 2
        await self.runtime.client.async_set_profile_service(
            profile_pk,
            service_pk,
            enabled=enabled,
            action_do=action_do,
        )
        self.runtime.registry.services_by_profile[profile_pk][service_pk] = replace(
            service_row,
            enabled=enabled,
            action_do=action_do,
        )
        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    async def async_set_profile_option_toggle(
        self, profile_pk: str, option_pk: str, enabled: bool
    ) -> None:
        """Enable or disable one toggle-style profile option."""
        option_row = self.runtime.registry.options_by_profile[profile_pk][option_pk]
        payload_value: str | None = None
        next_value_key = "1" if enabled else None
        if option_row.option_type == "field":
            payload_value = option_row.default_value_key if enabled else None
            next_value_key = payload_value
        await self.runtime.client.async_set_profile_option(
            profile_pk,
            option_pk,
            enabled=enabled,
            value=payload_value,
        )
        self.runtime.registry.options_by_profile[profile_pk][option_pk] = replace(
            option_row,
            current_value_key=next_value_key,
        )
        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    async def async_set_profile_option_select(
        self, profile_pk: str, option_pk: str, option_label: str
    ) -> None:
        """Set one select-style profile option."""
        option_row = self.runtime.registry.options_by_profile[profile_pk][option_pk]
        selected_value = option_row.choice_value_for_label(option_label)
        await self.runtime.client.async_set_profile_option(
            profile_pk,
            option_pk,
            enabled=selected_value is not None,
            value=selected_value,
        )
        self.runtime.registry.options_by_profile[profile_pk][option_pk] = replace(
            option_row,
            current_value_key=selected_value,
        )
        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    async def async_set_default_rule_mode(self, profile_pk: str, mode: str) -> None:
        """Set the current default-rule mode for one profile."""
        default_rule_row = self.runtime.registry.default_rules_by_profile[profile_pk]
        action_do, via = default_rule_action_from_mode(mode)
        await self.runtime.client.async_set_profile_default_rule(
            profile_pk,
            action_do=action_do,
            via=via,
        )
        self.runtime.registry.default_rules_by_profile[profile_pk] = replace(
            default_rule_row,
            enabled=True,
            action_do=action_do,
            via=via,
        )
        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    async def async_set_rule_group_mode(
        self, profile_pk: str, group_pk: str, mode: str
    ) -> None:
        """Set the current folder-rule mode for one profile group."""
        group_row = self.runtime.registry.rule_groups_by_profile[profile_pk][group_pk]
        enabled, action_do = rule_group_action_from_mode(mode)
        await self.runtime.client.async_set_profile_group(
            profile_pk,
            group_pk,
            name=group_row.name,
            enabled=enabled,
            action_do=action_do,
        )
        self.runtime.registry.rule_groups_by_profile[profile_pk][group_pk] = replace(
            group_row,
            enabled=enabled,
            action_do=action_do,
        )
        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    async def async_set_rule_enabled(
        self, profile_pk: str, rule_identity: str, enabled: bool
    ) -> None:
        """Enable or disable one selected rule."""
        rule_row = self.runtime.registry.rules_by_profile[profile_pk][rule_identity]
        await self.runtime.client.async_set_profile_rule(
            profile_pk,
            rule_row.rule_pk,
            enabled=enabled,
            action_do=rule_row.action_do,
            group_pk=rule_row.group_pk,
            ttl=rule_row.ttl,
        )
        await self.runtime.active_coordinator.async_refresh()

    @staticmethod
    def _require_string(profile_payload: dict[str, Any], key: str) -> str:
        """Return a required profile field as a string."""
        value = profile_payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"Profile payload is missing required string field {key!r}"
            )
        return value
