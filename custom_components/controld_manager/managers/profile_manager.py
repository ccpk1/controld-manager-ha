"""Profile normalization and orchestration for Control D."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..models import (
    ControlDDefaultRule,
    ControlDFilter,
    ControlDProfileOption,
    ControlDProfileSummary,
    ControlDRule,
    ControlDRuleGroup,
    ControlDService,
    build_rule_identity,
    default_rule_action_from_mode,
    normalize_service_mode,
    rule_action_do_from_key,
    rule_group_action_from_mode,
)
from .base_manager import BaseManager


class ProfileManager(BaseManager):
    """Own profile normalization and profile-scoped business logic."""

    def _filter_row(self, profile_pk: str, filter_pk: str) -> ControlDFilter:
        """Return one cached filter row from the current registry."""
        return self.runtime.registry.filters_by_profile[profile_pk][filter_pk]

    def _service_row(self, profile_pk: str, service_pk: str) -> ControlDService:
        """Return one cached service row from the current registry."""
        return self.runtime.registry.services_by_profile[profile_pk][service_pk]

    def _option_row(self, profile_pk: str, option_pk: str) -> ControlDProfileOption:
        """Return one cached profile option row from the current registry."""
        return self.runtime.registry.options_by_profile[profile_pk][option_pk]

    def _default_rule_row(self, profile_pk: str) -> ControlDDefaultRule:
        """Return one cached default-rule row from the current registry."""
        return self.runtime.registry.default_rules_by_profile[profile_pk]

    def _rule_group_row(self, profile_pk: str, group_pk: str) -> ControlDRuleGroup:
        """Return one cached rule-group row from the current registry."""
        return self.runtime.registry.rule_groups_by_profile[profile_pk][group_pk]

    def _rule_row(self, profile_pk: str, rule_identity: str) -> ControlDRule:
        """Return one cached rule row from the current registry."""
        return self.runtime.registry.rules_by_profile[profile_pk][rule_identity]

    def _updated_filter_rows(
        self, profile_filters: dict[str, frozenset[str]]
    ) -> list[tuple[str, str, ControlDFilter]]:
        """Resolve the filter rows targeted by one bulk write request."""
        updated_filters: list[tuple[str, str, ControlDFilter]] = []
        for profile_pk, filter_pks in profile_filters.items():
            for filter_pk in filter_pks:
                updated_filters.append(
                    (profile_pk, filter_pk, self._filter_row(profile_pk, filter_pk))
                )
        return updated_filters

    def _update_cached_filter(
        self,
        profile_pk: str,
        filter_pk: str,
        filter_row: ControlDFilter,
        *,
        enabled: bool,
        selected_level_slug: str | None,
    ) -> None:
        """Update one cached filter row after a successful upstream write."""
        self.runtime.registry.filters_by_profile[profile_pk][filter_pk] = replace(
            filter_row,
            enabled=enabled,
            selected_level_slug=selected_level_slug,
        )

    def _update_cached_service(
        self,
        profile_pk: str,
        service_pk: str,
        service_row: ControlDService,
        *,
        enabled: bool,
        action_do: int,
    ) -> None:
        """Update one cached service row after a successful upstream write."""
        self.runtime.registry.services_by_profile[profile_pk][service_pk] = replace(
            service_row,
            enabled=enabled,
            action_do=action_do,
        )

    def _update_cached_option(
        self,
        profile_pk: str,
        option_pk: str,
        option_row: ControlDProfileOption,
        *,
        current_value_key: str | None,
    ) -> None:
        """Update one cached profile-option row after a successful write."""
        self.runtime.registry.options_by_profile[profile_pk][option_pk] = replace(
            option_row,
            current_value_key=current_value_key,
        )

    def _update_cached_default_rule(
        self,
        profile_pk: str,
        default_rule_row: ControlDDefaultRule,
        *,
        enabled: bool,
        action_do: int,
        via: str | None,
    ) -> None:
        """Update one cached default-rule row after a successful write."""
        self.runtime.registry.default_rules_by_profile[profile_pk] = replace(
            default_rule_row,
            enabled=enabled,
            action_do=action_do,
            via=via,
        )

    def _update_cached_rule_group(
        self,
        profile_pk: str,
        group_pk: str,
        group_row: ControlDRuleGroup,
        *,
        enabled: bool,
        action_do: int | None,
    ) -> None:
        """Update one cached rule-group row after a successful write."""
        self.runtime.registry.rule_groups_by_profile[profile_pk][group_pk] = replace(
            group_row,
            enabled=enabled,
            action_do=action_do,
        )

    def _update_cached_rule(
        self,
        profile_pk: str,
        rule_identity: str,
        rule_row: ControlDRule,
        *,
        enabled: bool,
        action_do: int | None = None,
        ttl: int | None = None,
        comment: str | None = None,
    ) -> None:
        """Update one cached rule row after a successful write."""
        self.runtime.registry.rules_by_profile[profile_pk][rule_identity] = replace(
            rule_row,
            enabled=enabled,
            action_do=(rule_row.action_do if action_do is None else action_do),
            ttl=(rule_row.ttl if ttl is None else ttl),
            comment=(rule_row.comment if comment is None else comment),
        )

    def _create_cached_rule(
        self,
        profile_pk: str,
        *,
        hostname: str,
        group_pk: str | None,
        group_name: str | None,
        enabled: bool,
        action_do: int,
        comment: str,
        ttl: int | None,
    ) -> None:
        """Insert one newly created rule into the cached registry."""
        rules_by_identity = self.runtime.registry.rules_by_profile[profile_pk]
        next_order = (
            max((rule_row.order for rule_row in rules_by_identity.values()), default=0)
            + 1
        )
        identity = build_rule_identity(group_pk, hostname)
        rules_by_identity[identity] = ControlDRule(
            identity=identity,
            rule_pk=hostname,
            order=next_order,
            group_pk=group_pk,
            group_name=group_name,
            enabled=enabled,
            action_do=action_do,
            comment=comment,
            ttl=ttl,
        )

    def _delete_cached_rule(self, profile_pk: str, rule_identity: str) -> None:
        """Remove one deleted rule from the cached registry."""
        self.runtime.registry.rules_by_profile[profile_pk].pop(rule_identity, None)

    def _schedule_runtime_refresh(self) -> None:
        """Push optimistic state to listeners and queue a background refresh."""
        self.runtime.active_coordinator.async_update_listeners()
        self.runtime.active_coordinator.hass.async_create_task(
            self.runtime.active_coordinator.async_refresh()
        )

    @staticmethod
    def _resolved_rule_write_state(
        *,
        current_enabled: bool,
        current_action_do: int,
        current_comment: str,
        current_ttl: int | None,
        enabled: bool | None,
        mode: str | None,
        ttl: int | None,
        comment: str | None,
    ) -> tuple[bool, int, str, int | None]:
        """Resolve the effective rule write values from one optional mutation."""
        next_enabled = current_enabled if enabled is None else enabled
        next_action_do = (
            current_action_do if mode is None else rule_action_do_from_key(mode)
        )
        next_comment = current_comment if comment is None else comment
        next_ttl = current_ttl if ttl is None else ttl
        return next_enabled, next_action_do, next_comment, next_ttl

    @staticmethod
    def _service_write_payload(
        mode: str,
        service_row: ControlDService,
    ) -> tuple[bool, int]:
        """Translate one Home Assistant service mode into upstream fields."""
        normalized_mode = normalize_service_mode(mode)
        enabled = normalized_mode != "off"
        action_do = service_row.action_do
        if normalized_mode == "blocked":
            action_do = 0
        elif normalized_mode == "bypassed":
            action_do = 1
        elif normalized_mode == "redirected":
            action_do = 2
        return enabled, action_do

    @staticmethod
    def _toggle_option_write_payload(
        option_row: ControlDProfileOption, enabled: bool
    ) -> tuple[str | None, str | None]:
        """Translate a toggle request into payload and cached option values."""
        payload_value: str | None = None
        next_value_key = "1" if enabled else None
        if option_row.option_type == "field":
            payload_value = option_row.default_value_key if enabled else None
            next_value_key = payload_value
        return payload_value, next_value_key

    async def _async_write_filter_state(
        self,
        profile_pk: str,
        filter_pk: str,
        *,
        enabled: bool,
        action_do: int,
        level_slug: str | None,
        selected_level_slug: str | None,
    ) -> None:
        """Write one filter change upstream and update the cached registry row."""
        filter_row = self._filter_row(profile_pk, filter_pk)
        await self.runtime.client.async_set_profile_filter(
            profile_pk,
            filter_pk,
            enabled=enabled,
            action_do=action_do,
            level_slug=level_slug,
        )
        self._update_cached_filter(
            profile_pk,
            filter_pk,
            filter_row,
            enabled=enabled,
            selected_level_slug=selected_level_slug,
        )

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
        await self.async_set_filters_enabled(
            {profile_pk: frozenset({filter_pk})}, enabled
        )

    async def async_set_filters_enabled(
        self, profile_filters: dict[str, frozenset[str]], enabled: bool
    ) -> None:
        """Enable or disable one or more filters across targeted profiles."""
        updated_filters = self._updated_filter_rows(profile_filters)

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
            self._update_cached_filter(
                profile_pk,
                filter_pk,
                filter_row,
                enabled=enabled,
                selected_level_slug=filter_row.effective_level_slug,
            )

        self._schedule_runtime_refresh()

    async def async_set_filter_mode(
        self, profile_pk: str, filter_pk: str, level_slug: str
    ) -> None:
        """Set the selected mode for one filter."""
        filter_row = self._filter_row(profile_pk, filter_pk)
        await self._async_write_filter_state(
            profile_pk,
            filter_pk,
            enabled=True,
            action_do=filter_row.action_do,
            level_slug=level_slug,
            selected_level_slug=level_slug,
        )
        self._schedule_runtime_refresh()

    async def async_set_service_mode(
        self, profile_pk: str, service_pk: str, mode: str
    ) -> None:
        """Set the selected mode for one service rule."""
        service_row = self._service_row(profile_pk, service_pk)
        enabled, action_do = self._service_write_payload(mode, service_row)
        await self.runtime.client.async_set_profile_service(
            profile_pk,
            service_pk,
            enabled=enabled,
            action_do=action_do,
        )
        self._update_cached_service(
            profile_pk,
            service_pk,
            service_row,
            enabled=enabled,
            action_do=action_do,
        )
        self._schedule_runtime_refresh()

    async def async_set_services_mode(
        self,
        profile_services: dict[str, frozenset[str]],
        mode: str,
        *,
        service_rows_by_profile: dict[str, dict[str, ControlDService]] | None = None,
    ) -> None:
        """Set the selected mode for one or more services across profiles."""
        updated_services: list[tuple[str, str, ControlDService, bool, int]] = []

        for profile_pk, service_pks in profile_services.items():
            for service_pk in service_pks:
                if (
                    service_rows_by_profile
                    and service_pk in service_rows_by_profile.get(profile_pk, {})
                ):
                    service_row = service_rows_by_profile[profile_pk][service_pk]
                else:
                    service_row = self._service_row(profile_pk, service_pk)
                enabled, action_do = self._service_write_payload(mode, service_row)
                updated_services.append(
                    (profile_pk, service_pk, service_row, enabled, action_do)
                )

        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_service(
                    profile_pk,
                    service_pk,
                    enabled=enabled,
                    action_do=action_do,
                )
                for profile_pk, service_pk, _, enabled, action_do in updated_services
            )
        )

        for profile_pk, service_pk, service_row, enabled, action_do in updated_services:
            self._update_cached_service(
                profile_pk,
                service_pk,
                service_row,
                enabled=enabled,
                action_do=action_do,
            )

        self._schedule_runtime_refresh()

    async def async_set_profile_options_state(
        self,
        profile_options: dict[str, frozenset[str]],
        *,
        enabled: bool | None,
        value: str | None,
    ) -> None:
        """Update one or more profile options across targeted profiles."""
        updated_options: list[
            tuple[str, str, ControlDProfileOption, bool, str | None, str | None]
        ] = []

        for profile_pk, option_pks in profile_options.items():
            for option_pk in option_pks:
                option_row = self._option_row(profile_pk, option_pk)
                if option_row.entity_kind == "toggle":
                    if (
                        option_row.option_type == "field"
                        and option_row.option_pk in {"ttl_blck", "ttl_spff", "ttl_pass"}
                        and value is not None
                    ):
                        next_enabled = True if enabled is None else enabled
                        updated_options.append(
                            (
                                profile_pk,
                                option_pk,
                                option_row,
                                next_enabled,
                                value,
                                value,
                            )
                        )
                        continue
                    assert enabled is not None
                    payload_value, next_value_key = self._toggle_option_write_payload(
                        option_row,
                        enabled,
                    )
                    updated_options.append(
                        (
                            profile_pk,
                            option_pk,
                            option_row,
                            enabled,
                            payload_value,
                            next_value_key,
                        )
                    )
                    continue

                if value is not None:
                    selected_value = option_row.choice_value_for_input(value)
                elif enabled is False:
                    selected_value = None
                else:
                    selected_value = option_row.default_value_key
                    if selected_value is None and option_row.choices:
                        selected_value = option_row.choices[0].value
                updated_options.append(
                    (
                        profile_pk,
                        option_pk,
                        option_row,
                        selected_value is not None,
                        selected_value,
                        selected_value,
                    )
                )

        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_option(
                    profile_pk,
                    option_pk,
                    enabled=next_enabled,
                    value=payload_value,
                )
                for (
                    profile_pk,
                    option_pk,
                    _,
                    next_enabled,
                    payload_value,
                    _,
                ) in updated_options
            )
        )

        for (
            profile_pk,
            option_pk,
            option_row,
            _,
            _,
            next_value_key,
        ) in updated_options:
            self._update_cached_option(
                profile_pk,
                option_pk,
                option_row,
                current_value_key=next_value_key,
            )

        self._schedule_runtime_refresh()

    async def async_set_profile_option_toggle(
        self, profile_pk: str, option_pk: str, enabled: bool
    ) -> None:
        """Enable or disable one toggle-style profile option."""
        option_row = self._option_row(profile_pk, option_pk)
        payload_value, next_value_key = self._toggle_option_write_payload(
            option_row,
            enabled,
        )
        await self.runtime.client.async_set_profile_option(
            profile_pk,
            option_pk,
            enabled=enabled,
            value=payload_value,
        )
        self._update_cached_option(
            profile_pk,
            option_pk,
            option_row,
            current_value_key=next_value_key,
        )
        self._schedule_runtime_refresh()

    async def async_set_profile_option_select(
        self, profile_pk: str, option_pk: str, option_label: str
    ) -> None:
        """Set one select-style profile option."""
        option_row = self._option_row(profile_pk, option_pk)
        selected_value = option_row.choice_value_for_label(option_label)
        await self.runtime.client.async_set_profile_option(
            profile_pk,
            option_pk,
            enabled=selected_value is not None,
            value=selected_value,
        )
        self._update_cached_option(
            profile_pk,
            option_pk,
            option_row,
            current_value_key=selected_value,
        )
        self._schedule_runtime_refresh()

    async def async_set_default_rule_mode(self, profile_pk: str, mode: str) -> None:
        """Set the current default-rule mode for one profile."""
        default_rule_row = self._default_rule_row(profile_pk)
        action_do, via = default_rule_action_from_mode(mode)
        await self.runtime.client.async_set_profile_default_rule(
            profile_pk,
            action_do=action_do,
            via=via,
        )
        self._update_cached_default_rule(
            profile_pk,
            default_rule_row,
            enabled=True,
            action_do=action_do,
            via=via,
        )
        self._schedule_runtime_refresh()

    async def async_set_default_rules_mode(
        self, profile_pks: frozenset[str], mode: str
    ) -> None:
        """Set the default-rule mode across one or more targeted profiles."""
        action_do, via = default_rule_action_from_mode(mode)
        updated_default_rules: list[tuple[str, ControlDDefaultRule]] = [
            (profile_pk, self._default_rule_row(profile_pk))
            for profile_pk in profile_pks
        ]

        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_default_rule(
                    profile_pk,
                    action_do=action_do,
                    via=via,
                )
                for profile_pk, _ in updated_default_rules
            )
        )

        for profile_pk, default_rule_row in updated_default_rules:
            self._update_cached_default_rule(
                profile_pk,
                default_rule_row,
                enabled=True,
                action_do=action_do,
                via=via,
            )

        self._schedule_runtime_refresh()

    async def async_set_rule_group_mode(
        self, profile_pk: str, group_pk: str, mode: str
    ) -> None:
        """Set the current folder-rule mode for one profile group."""
        group_row = self._rule_group_row(profile_pk, group_pk)
        enabled, action_do = rule_group_action_from_mode(mode)
        await self.runtime.client.async_set_profile_group(
            profile_pk,
            group_pk,
            name=group_row.name,
            enabled=enabled,
            action_do=action_do,
        )
        self._update_cached_rule_group(
            profile_pk,
            group_pk,
            group_row,
            enabled=enabled,
            action_do=action_do,
        )
        self._schedule_runtime_refresh()

    async def async_set_rule_enabled(
        self, profile_pk: str, rule_identity: str, enabled: bool
    ) -> None:
        """Enable or disable one selected rule."""
        rule_row = self._rule_row(profile_pk, rule_identity)
        await self.runtime.client.async_set_profile_rule(
            profile_pk,
            rule_row.rule_pk,
            enabled=enabled,
            action_do=rule_row.action_do,
            group_pk=rule_row.group_pk,
            ttl=rule_row.ttl,
        )
        self._update_cached_rule(
            profile_pk,
            rule_identity,
            rule_row,
            enabled=enabled,
        )
        self._schedule_runtime_refresh()

    async def async_set_rules_enabled(
        self, profile_rules: dict[str, frozenset[str]], enabled: bool
    ) -> None:
        """Enable or disable one or more selected rules across profiles."""
        updated_rules: list[tuple[str, str, ControlDRule]] = []

        for profile_pk, rule_identities in profile_rules.items():
            for rule_identity in rule_identities:
                updated_rules.append(
                    (
                        profile_pk,
                        rule_identity,
                        self._rule_row(profile_pk, rule_identity),
                    )
                )

        await asyncio.gather(
            *(
                self.runtime.client.async_set_profile_rule(
                    profile_pk,
                    rule_row.rule_pk,
                    enabled=enabled,
                    action_do=rule_row.action_do,
                    group_pk=rule_row.group_pk,
                    ttl=rule_row.ttl,
                )
                for profile_pk, _, rule_row in updated_rules
            )
        )

        for profile_pk, rule_identity, rule_row in updated_rules:
            self._update_cached_rule(
                profile_pk,
                rule_identity,
                rule_row,
                enabled=enabled,
            )

        self._schedule_runtime_refresh()

    async def async_set_rules_state(
        self,
        profile_rules: dict[str, frozenset[str]],
        *,
        enabled: bool | None,
        mode: str | None,
        ttl: int | None,
        comment: str | None,
    ) -> None:
        """Update one or more selected rules across profiles."""
        updated_rules: list[
            tuple[
                str,
                str,
                ControlDRule,
                bool,
                int,
                str,
                int | None,
                int | None,
                bool,
            ]
        ] = []

        for profile_pk, rule_identities in profile_rules.items():
            for rule_identity in rule_identities:
                rule_row = self._rule_row(profile_pk, rule_identity)
                (
                    next_enabled,
                    next_action_do,
                    next_comment,
                    payload_ttl,
                ) = self._resolved_rule_write_state(
                    current_enabled=rule_row.enabled,
                    current_action_do=rule_row.action_do,
                    current_comment=rule_row.comment,
                    current_ttl=rule_row.ttl,
                    enabled=enabled,
                    mode=mode,
                    ttl=ttl,
                    comment=comment,
                )
                uses_rich_update = comment is not None or ttl is not None
                updated_rules.append(
                    (
                        profile_pk,
                        rule_identity,
                        rule_row,
                        next_enabled,
                        next_action_do,
                        next_comment,
                        payload_ttl,
                        payload_ttl,
                        uses_rich_update,
                    )
                )

        await asyncio.gather(
            *(
                (
                    self.runtime.client.async_update_profile_rule_rich(
                        profile_pk,
                        rule_row.rule_pk,
                        enabled=next_enabled,
                        action_do=next_action_do,
                        group_pk=rule_row.group_pk,
                        comment=next_comment,
                        ttl=payload_ttl,
                    )
                    if uses_rich_update
                    else self.runtime.client.async_set_profile_rule(
                        profile_pk,
                        rule_row.rule_pk,
                        enabled=next_enabled,
                        action_do=next_action_do,
                        group_pk=rule_row.group_pk,
                        ttl=payload_ttl,
                        comment=next_comment,
                    )
                )
                for (
                    profile_pk,
                    _,
                    rule_row,
                    next_enabled,
                    next_action_do,
                    next_comment,
                    payload_ttl,
                    _,
                    uses_rich_update,
                ) in updated_rules
            )
        )

        for (
            profile_pk,
            rule_identity,
            rule_row,
            next_enabled,
            next_action_do,
            next_comment,
            _,
            cached_ttl,
            _,
        ) in updated_rules:
            self._update_cached_rule(
                profile_pk,
                rule_identity,
                rule_row,
                enabled=next_enabled,
                action_do=next_action_do,
                ttl=cached_ttl,
                comment=next_comment,
            )

        self._schedule_runtime_refresh()

    async def async_create_rules(
        self,
        profile_pks: frozenset[str],
        *,
        hostnames: tuple[str, ...],
        group_pks_by_profile: dict[str, str | None],
        group_names_by_profile: dict[str, str | None],
        enabled: bool | None,
        mode: str | None,
        ttl: int | None,
        comment: str | None,
    ) -> None:
        """Create one or more rules across one or more selected profiles."""
        create_requests: list[
            tuple[str, str | None, str | None, bool, int, str, int | None]
        ] = []

        for profile_pk in profile_pks:
            group_pk = group_pks_by_profile[profile_pk]
            group_name = group_names_by_profile[profile_pk]
            next_enabled, next_action_do, next_comment, next_ttl = (
                self._resolved_rule_write_state(
                    current_enabled=True,
                    current_action_do=0,
                    current_comment="",
                    current_ttl=None,
                    enabled=enabled,
                    mode=mode,
                    ttl=ttl,
                    comment=comment,
                )
            )
            create_requests.append(
                (
                    profile_pk,
                    group_pk,
                    group_name,
                    next_enabled,
                    next_action_do,
                    next_comment,
                    next_ttl,
                )
            )

        await asyncio.gather(
            *(
                self.runtime.client.async_create_profile_rules(
                    profile_pk,
                    list(hostnames),
                    enabled=next_enabled,
                    action_do=next_action_do,
                    group_pk=group_pk,
                    comment=next_comment,
                    ttl=next_ttl,
                )
                for (
                    profile_pk,
                    group_pk,
                    _,
                    next_enabled,
                    next_action_do,
                    next_comment,
                    next_ttl,
                ) in create_requests
            )
        )

        for (
            profile_pk,
            group_pk,
            group_name,
            next_enabled,
            next_action_do,
            next_comment,
            next_ttl,
        ) in create_requests:
            for hostname in hostnames:
                self._create_cached_rule(
                    profile_pk,
                    hostname=hostname,
                    group_pk=group_pk,
                    group_name=group_name,
                    enabled=next_enabled,
                    action_do=next_action_do,
                    comment=next_comment,
                    ttl=next_ttl,
                )

        self._schedule_runtime_refresh()

    async def async_delete_rules(
        self,
        profile_rules: dict[str, frozenset[str]],
    ) -> None:
        """Delete one or more selected rules across profiles."""
        delete_requests: list[tuple[str, list[str], tuple[str, ...]]] = []

        for profile_pk, rule_identities in profile_rules.items():
            hostnames = [
                self._rule_row(profile_pk, rule_identity).rule_pk
                for rule_identity in rule_identities
            ]
            delete_requests.append((profile_pk, hostnames, tuple(rule_identities)))

        await asyncio.gather(
            *(
                self.runtime.client.async_delete_profile_rules(profile_pk, hostnames)
                for profile_pk, hostnames, _ in delete_requests
            )
        )

        for profile_pk, _, deleted_rule_identities in delete_requests:
            for rule_identity in deleted_rule_identities:
                self._delete_cached_rule(profile_pk, rule_identity)

        self._schedule_runtime_refresh()

    @staticmethod
    def _require_string(profile_payload: dict[str, Any], key: str) -> str:
        """Return a required profile field as a string."""
        value = profile_payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"Profile payload is missing required string field {key!r}"
            )
        return value
