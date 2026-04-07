"""Reusable selector-resolution helpers for Control D services."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DOMAIN,
    TRANS_KEY_FILTER_NAME_AMBIGUOUS,
    TRANS_KEY_FILTER_NAME_NOT_FOUND,
    TRANS_KEY_FILTER_TARGET_REQUIRED,
)
from .models import (
    ControlDFilter,
    ControlDManagerRuntime,
    ControlDProfileOption,
    ControlDRule,
    ControlDRuleGroup,
    ControlDService,
)

ControlDManagerConfigEntry = ConfigEntry[ControlDManagerRuntime]


def _resolve_selected_filter_pks(
    entry: ControlDManagerConfigEntry,
    profile_pks: frozenset[str],
    *,
    requested_filter_ids: list[str],
    requested_filter_names: list[str],
) -> dict[str, frozenset[str]]:
    """Resolve explicit filter selectors using a stable precedence order.

    Selection precedence is:
    1. `filter_id`
    2. `filter_name`
    """
    return _resolve_selected_profile_item_keys(
        profile_pks,
        requested_item_ids=requested_filter_ids,
        requested_item_names=requested_filter_names,
        items_for_profile=lambda profile_pk: _sorted_profile_filters(entry, profile_pk),
        item_id=lambda filter_row: filter_row.filter_pk,
        item_name=lambda filter_row: filter_row.name,
        required_message="Select at least one Control D filter by ID or name",
        required_translation_key=TRANS_KEY_FILTER_TARGET_REQUIRED,
        not_found_message=(
            "The selected Control D filter target could not be resolved for one "
            "or more targeted profiles"
        ),
        not_found_translation_key=TRANS_KEY_FILTER_NAME_NOT_FOUND,
        ambiguous_message="The selected Control D filter target is ambiguous",
        ambiguous_translation_key=TRANS_KEY_FILTER_NAME_AMBIGUOUS,
    )


def _resolve_selected_service_pks(
    entry: ControlDManagerConfigEntry,
    profile_pks: frozenset[str],
    *,
    requested_service_ids: list[str],
    requested_service_names: list[str],
) -> dict[str, frozenset[str]]:
    """Resolve service selectors across targeted profiles for future services."""
    return _resolve_selected_profile_item_keys(
        profile_pks,
        requested_item_ids=requested_service_ids,
        requested_item_names=requested_service_names,
        items_for_profile=lambda profile_pk: _sorted_profile_services(
            entry,
            profile_pk,
        ),
        item_id=lambda service_row: service_row.service_pk,
        item_name=lambda service_row: service_row.name,
        required_message="Select at least one Control D service by ID or name",
        not_found_message=(
            "The selected Control D service target could not be resolved for one "
            "or more targeted profiles"
        ),
        ambiguous_message="The selected Control D service target is ambiguous",
    )


def _resolve_selected_rule_group_pks(
    entry: ControlDManagerConfigEntry,
    profile_pks: frozenset[str],
    *,
    requested_group_ids: list[str],
    requested_group_names: list[str],
) -> dict[str, frozenset[str]]:
    """Resolve rule-group selectors across targeted profiles for future services."""
    return _resolve_selected_profile_item_keys(
        profile_pks,
        requested_item_ids=requested_group_ids,
        requested_item_names=requested_group_names,
        items_for_profile=lambda profile_pk: _sorted_profile_rule_groups(
            entry,
            profile_pk,
        ),
        item_id=lambda group_row: group_row.group_pk,
        item_name=lambda group_row: group_row.name,
        required_message="Select at least one Control D rule group by ID or name",
        not_found_message=(
            "The selected Control D rule-group target could not be resolved for "
            "one or more targeted profiles"
        ),
        ambiguous_message="The selected Control D rule-group target is ambiguous",
    )


def _resolve_selected_rule_identities(
    entry: ControlDManagerConfigEntry,
    profile_pks: frozenset[str],
    *,
    requested_rule_identities: list[str],
    requested_rule_comments: list[str],
) -> dict[str, frozenset[str]]:
    """Resolve rule selectors across targeted profiles for future services."""
    return _resolve_selected_profile_item_keys(
        profile_pks,
        requested_item_ids=requested_rule_identities,
        requested_item_names=requested_rule_comments,
        items_for_profile=lambda profile_pk: _sorted_profile_rules(entry, profile_pk),
        item_id=lambda rule_row: rule_row.identity,
        item_name=lambda rule_row: rule_row.comment or None,
        required_message="Select at least one Control D rule by identity or comment",
        not_found_message=(
            "The selected Control D rule target could not be resolved for one or "
            "more targeted profiles"
        ),
        ambiguous_message="The selected Control D rule target is ambiguous",
    )


def _resolve_selected_option_pks(
    entry: ControlDManagerConfigEntry,
    profile_pks: frozenset[str],
    *,
    requested_option_ids: list[str],
    requested_option_titles: list[str],
) -> dict[str, frozenset[str]]:
    """Resolve profile-option selectors across targeted profiles for future services."""
    return _resolve_selected_profile_item_keys(
        profile_pks,
        requested_item_ids=requested_option_ids,
        requested_item_names=requested_option_titles,
        items_for_profile=lambda profile_pk: _sorted_profile_options(entry, profile_pk),
        item_id=lambda option_row: option_row.option_pk,
        item_name=lambda option_row: option_row.title,
        required_message="Select at least one Control D profile option by ID or title",
        not_found_message=(
            "The selected Control D profile-option target could not be resolved "
            "for one or more targeted profiles"
        ),
        ambiguous_message="The selected Control D profile-option target is ambiguous",
    )


def _resolve_selected_profile_item_keys[
    ControlDItemRow: (
        ControlDFilter,
        ControlDProfileOption,
        ControlDRule,
        ControlDRuleGroup,
        ControlDService,
    )
](
    profile_pks: frozenset[str],
    *,
    requested_item_ids: list[str],
    requested_item_names: list[str],
    items_for_profile: Callable[[str], Iterable[ControlDItemRow]],
    item_id: Callable[[ControlDItemRow], str],
    item_name: Callable[[ControlDItemRow], str | None],
    required_message: str,
    not_found_message: str,
    ambiguous_message: str,
    required_translation_key: str | None = None,
    not_found_translation_key: str | None = None,
    ambiguous_translation_key: str | None = None,
) -> dict[str, frozenset[str]]:
    """Resolve profile-scoped item selectors using stable ID-before-name rules."""
    if requested_item_ids:
        return _resolve_profile_items_by_value(
            profile_pks,
            requested_values=requested_item_ids,
            items_for_profile=items_for_profile,
            item_id=item_id,
            matched_value=item_id,
            not_found_message=not_found_message,
            not_found_translation_key=not_found_translation_key,
            ambiguous_message=ambiguous_message,
            ambiguous_translation_key=ambiguous_translation_key,
        )
    if requested_item_names:
        return _resolve_profile_items_by_value(
            profile_pks,
            requested_values=requested_item_names,
            items_for_profile=items_for_profile,
            item_id=item_id,
            matched_value=item_name,
            not_found_message=not_found_message,
            not_found_translation_key=not_found_translation_key,
            ambiguous_message=ambiguous_message,
            ambiguous_translation_key=ambiguous_translation_key,
        )

    raise _service_validation_error(
        required_message,
        translation_key=required_translation_key,
    )


def _resolve_profile_items_by_value[
    ControlDItemRow: (
        ControlDFilter,
        ControlDProfileOption,
        ControlDRule,
        ControlDRuleGroup,
        ControlDService,
    )
](
    profile_pks: frozenset[str],
    *,
    requested_values: list[str],
    items_for_profile: Callable[[str], Iterable[ControlDItemRow]],
    item_id: Callable[[ControlDItemRow], str],
    matched_value: Callable[[ControlDItemRow], str | None],
    not_found_message: str,
    ambiguous_message: str,
    not_found_translation_key: str | None = None,
    ambiguous_translation_key: str | None = None,
) -> dict[str, frozenset[str]]:
    """Resolve one requested ID or display value family across profile-scoped rows."""
    resolved_items: dict[str, frozenset[str]] = {}

    for profile_pk in profile_pks:
        resolved_item_ids: set[str] = set()
        items = tuple(items_for_profile(profile_pk))
        for requested_value in requested_values:
            normalized_requested_value = _normalize_name(requested_value)
            matches = [
                item_id(item_row)
                for item_row in items
                if (candidate := matched_value(item_row)) is not None
                if _normalize_name(candidate) == normalized_requested_value
            ]
            if len(matches) == 1:
                resolved_item_ids.add(matches[0])
                continue
            if len(matches) > 1:
                raise _service_validation_error(
                    ambiguous_message,
                    translation_key=ambiguous_translation_key,
                )
            raise _service_validation_error(
                not_found_message,
                translation_key=not_found_translation_key,
            )
        resolved_items[profile_pk] = frozenset(resolved_item_ids)

    return resolved_items


def _service_validation_error(
    message: str,
    *,
    translation_key: str | None = None,
) -> ServiceValidationError:
    """Build one translatable or plain service validation error."""
    if translation_key is None:
        return ServiceValidationError(message)
    return ServiceValidationError(
        message,
        translation_domain=DOMAIN,
        translation_key=translation_key,
    )


def _sorted_profile_filters(
    entry: ControlDManagerConfigEntry, profile_pk: str
) -> tuple[ControlDFilter, ...]:
    """Return one profile's filters with native rows ahead of 3rd-party rows."""
    filters = entry.runtime_data.registry.filters_by_profile.get(
        profile_pk, {}
    ).values()
    return tuple(
        sorted(
            filters,
            key=lambda filter_row: (
                filter_row.external,
                _normalize_name(filter_row.name),
                _normalize_name(filter_row.filter_pk),
            ),
        )
    )


def _sorted_profile_services(
    entry: ControlDManagerConfigEntry, profile_pk: str
) -> tuple[ControlDService, ...]:
    """Return one profile's services in stable display order."""
    services = entry.runtime_data.registry.services_by_profile.get(
        profile_pk, {}
    ).values()
    return tuple(
        sorted(
            services,
            key=lambda service_row: (
                _normalize_name(service_row.category_name),
                _normalize_name(service_row.name),
                _normalize_name(service_row.service_pk),
            ),
        )
    )


def _sorted_profile_rule_groups(
    entry: ControlDManagerConfigEntry, profile_pk: str
) -> tuple[ControlDRuleGroup, ...]:
    """Return one profile's rule groups in stable display order."""
    groups = entry.runtime_data.registry.rule_groups_by_profile.get(
        profile_pk, {}
    ).values()
    return tuple(
        sorted(
            groups,
            key=lambda group_row: (
                _normalize_name(group_row.name),
                _normalize_name(group_row.group_pk),
            ),
        )
    )


def _sorted_profile_rules(
    entry: ControlDManagerConfigEntry, profile_pk: str
) -> tuple[ControlDRule, ...]:
    """Return one profile's rules in stable display order."""
    rules = entry.runtime_data.registry.rules_by_profile.get(profile_pk, {}).values()
    return tuple(
        sorted(
            rules,
            key=lambda rule_row: (
                _normalize_name(rule_row.group_name or ""),
                rule_row.order,
                _normalize_name(rule_row.comment),
                _normalize_name(rule_row.identity),
            ),
        )
    )


def _sorted_profile_options(
    entry: ControlDManagerConfigEntry, profile_pk: str
) -> tuple[ControlDProfileOption, ...]:
    """Return one profile's options in stable display order."""
    options = entry.runtime_data.registry.options_by_profile.get(
        profile_pk, {}
    ).values()
    return tuple(
        sorted(
            options,
            key=lambda option_row: (
                _normalize_name(option_row.title),
                _normalize_name(option_row.option_pk),
            ),
        )
    )


def _normalize_name(value: str) -> str:
    """Normalize a user-supplied name for case-insensitive lookup."""
    return re.sub(r"\s+", " ", value).strip().casefold()
