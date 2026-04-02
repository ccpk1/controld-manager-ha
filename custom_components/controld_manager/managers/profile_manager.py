"""Profile normalization and orchestration for Control D."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..models import ControlDProfileSummary
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

    async def async_pause_profiles(self, profile_pks: set[str], minutes: int) -> None:
        """Pause one or more profiles until a future timestamp."""
        paused_until = dt_util.utcnow() + timedelta(minutes=minutes)
        disable_ttl = int(paused_until.timestamp())
        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_pause_until(
                    profile_pk, disable_ttl
                )
                for profile_pk in profile_pks
            )
        )
        await self.runtime.active_coordinator.async_refresh()

    async def async_resume_profiles(self, profile_pks: set[str]) -> None:
        """Resume one or more paused profiles immediately."""
        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_pause_until(profile_pk, 0)
                for profile_pk in profile_pks
            )
        )
        await self.runtime.active_coordinator.async_refresh()

    async def async_set_filter_enabled(
        self, profile_pk: str, filter_pk: str, enabled: bool
    ) -> None:
        """Enable or disable one profile filter."""
        filter_row = self.runtime.registry.filters_by_profile[profile_pk][filter_pk]
        await self.runtime.client.async_set_profile_filter(
            profile_pk,
            filter_pk,
            enabled=enabled,
            action_do=filter_row.action_do,
            level_slug=filter_row.selected_level_slug,
        )
        await self.runtime.active_coordinator.async_refresh()

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
        await self.runtime.active_coordinator.async_refresh()

    async def async_set_service_enabled(
        self, profile_pk: str, service_pk: str, enabled: bool
    ) -> None:
        """Enable or disable one service rule."""
        service_row = self.runtime.registry.services_by_profile[profile_pk][service_pk]
        await self.runtime.client.async_set_profile_service(
            profile_pk,
            service_pk,
            enabled=enabled,
            action_do=service_row.action_do,
        )
        await self.runtime.active_coordinator.async_refresh()

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
