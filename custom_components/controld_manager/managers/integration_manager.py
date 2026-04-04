"""Shared runtime orchestration for Control D."""

from __future__ import annotations

from typing import Any

from ..models import (
    ControlDDefaultRule,
    ControlDFilter,
    ControlDFilterLevel,
    ControlDInventoryPayload,
    ControlDProfileOption,
    ControlDProfileOptionChoice,
    ControlDRegistry,
    ControlDRule,
    ControlDRuleGroup,
    ControlDService,
    ControlDServiceCategory,
    ControlDUser,
    build_rule_identity,
)
from .base_manager import BaseManager
from .device_manager import DeviceManager
from .endpoint_manager import EndpointManager
from .entity_manager import EntityManager
from .profile_manager import ProfileManager


class IntegrationManager(BaseManager):
    """Own entry-scoped registry shaping and shared orchestration."""

    def __init__(
        self,
        profile_manager: ProfileManager,
        endpoint_manager: EndpointManager,
        device_manager: DeviceManager,
        entity_manager: EntityManager,
    ) -> None:
        """Initialize the integration manager."""
        super().__init__()
        self._profile_manager = profile_manager
        self._endpoint_manager = endpoint_manager
        self._device_manager = device_manager
        self._entity_manager = entity_manager

    def build_registry(self, inventory: ControlDInventoryPayload) -> ControlDRegistry:
        """Build a normalized registry from the raw inventory payload."""
        profiles = self._profile_manager.normalize_profiles(inventory.profiles)
        included_profile_pks = self.runtime.options.included_profile_pks(set(profiles))
        endpoints = self._endpoint_manager.normalize_endpoints(inventory.devices)
        service_categories = self._normalize_service_categories(
            inventory.service_categories
        )
        registry = ControlDRegistry(
            user=self._normalize_user(inventory.user),
            endpoint_inventory=self._endpoint_manager.summarize_inventory(
                inventory.devices, endpoints
            ),
            profiles=profiles,
            endpoints=endpoints,
            filters_by_profile={
                profile_pk: self._normalize_filters(detail.filters)
                for profile_pk, detail in inventory.profile_details.items()
                if profile_pk in included_profile_pks
            },
            default_rules_by_profile={
                profile_pk: default_rule
                for profile_pk, detail in inventory.profile_details.items()
                if profile_pk in included_profile_pks
                if (default_rule := self._normalize_default_rule(detail.default_rule))
                is not None
            },
            rule_groups_by_profile={
                profile_pk: self._normalize_rule_groups(detail.groups)
                for profile_pk, detail in inventory.profile_details.items()
                if profile_pk in included_profile_pks
            },
            services_by_profile={
                profile_pk: self._normalize_services(
                    detail.services,
                    service_categories,
                    self.runtime.options.profile_policy(
                        profile_pk
                    ).allowed_service_categories,
                    inventory.service_catalog,
                )
                for profile_pk, detail in inventory.profile_details.items()
                if profile_pk in included_profile_pks
            },
            rules_by_profile={
                profile_pk: self._normalize_rules(detail.groups, detail.rules)
                for profile_pk, detail in inventory.profile_details.items()
                if profile_pk in included_profile_pks
            },
            options_by_profile={
                profile_pk: self._normalize_profile_options(
                    inventory.option_catalog,
                    detail.options,
                )
                for profile_pk, detail in inventory.profile_details.items()
                if profile_pk in included_profile_pks
            },
            service_categories=service_categories,
        )
        self._device_manager.sync_registry(registry)
        self._entity_manager.sync_registry(registry)
        return registry

    @staticmethod
    def _normalize_service_categories(
        categories_payload: tuple[dict[str, Any], ...],
    ) -> dict[str, ControlDServiceCategory]:
        """Normalize the available service categories."""
        categories: dict[str, ControlDServiceCategory] = {}
        for payload in categories_payload:
            category_pk = IntegrationManager._require_string(payload, "PK")
            categories[category_pk] = ControlDServiceCategory(
                category_pk=category_pk,
                name=IntegrationManager._require_string(payload, "name"),
                description=IntegrationManager._optional_string(
                    payload.get("description")
                ),
                count=int(payload.get("count", 0) or 0),
            )
        return categories

    @staticmethod
    def _normalize_filters(
        filters_payload: tuple[dict[str, Any], ...],
    ) -> dict[str, ControlDFilter]:
        """Normalize profile filter rows."""
        filters: dict[str, ControlDFilter] = {}
        for payload in filters_payload:
            filter_pk = IntegrationManager._require_string(payload, "PK")
            action = IntegrationManager._mapping_or_empty(payload.get("action"))
            levels = tuple(
                ControlDFilterLevel(
                    slug=IntegrationManager._require_string(level_payload, "name"),
                    title=IntegrationManager._require_string(level_payload, "title"),
                    enabled=bool(level_payload.get("status", 0)),
                )
                for level_payload in payload.get("levels", [])
                if isinstance(level_payload, dict)
            )
            selected_level_slug = IntegrationManager._optional_string(action.get("lvl"))
            if selected_level_slug is None:
                selected_level_slug = next(
                    (level.slug for level in levels if level.enabled),
                    None,
                )
            filters[filter_pk] = ControlDFilter(
                filter_pk=filter_pk,
                name=IntegrationManager._require_string(payload, "name"),
                enabled=bool(payload.get("status", 0)),
                action_do=int(action.get("do", 0) or 0),
                selected_level_slug=selected_level_slug,
                levels=levels,
            )
        return filters

    @staticmethod
    def _normalize_default_rule(
        payload: dict[str, Any] | None,
    ) -> ControlDDefaultRule | None:
        """Normalize one default-rule payload."""
        if not isinstance(payload, dict):
            return None
        return ControlDDefaultRule(
            enabled=bool(payload.get("status", 0)),
            action_do=int(payload.get("do", 0) or 0),
            via=IntegrationManager._optional_string(payload.get("via")),
        )

    @staticmethod
    def _normalize_services(
        services_payload: tuple[dict[str, Any], ...],
        service_categories: dict[str, ControlDServiceCategory],
        enabled_categories: frozenset[str],
        service_catalog_payload: tuple[dict[str, Any], ...],
    ) -> dict[str, ControlDService]:
        """Normalize service rows for the categories enabled by policy."""
        live_services: dict[str, dict[str, Any]] = {}
        for payload in services_payload:
            service_pk = IntegrationManager._require_string(payload, "PK")
            live_services[service_pk] = payload

        services: dict[str, ControlDService] = {}
        for payload in service_catalog_payload:
            category_pk = IntegrationManager._require_string(payload, "category")
            if category_pk not in enabled_categories:
                continue
            service_pk = IntegrationManager._require_string(payload, "PK")
            live_payload = live_services.get(service_pk, {})
            action = IntegrationManager._mapping_or_empty(live_payload.get("action"))
            category_name = service_categories.get(category_pk)
            services[service_pk] = ControlDService(
                service_pk=service_pk,
                name=IntegrationManager._require_string(payload, "name"),
                category_pk=category_pk,
                category_name=(
                    category_name.name
                    if category_name is not None
                    else category_pk.replace("_", " ").title()
                ),
                enabled=bool(action.get("status", 0)),
                action_do=(int(action["do"]) if "do" in action else 1),
                warning=IntegrationManager._optional_string(payload.get("warning")),
                unlock_location=IntegrationManager._optional_string(
                    payload.get("unlock_location")
                ),
            )
        return services

    @staticmethod
    def _normalize_rules(
        groups_payload: tuple[dict[str, Any], ...],
        rules_payload: tuple[dict[str, Any], ...],
    ) -> dict[str, ControlDRule]:
        """Normalize top-level and grouped rules."""
        groups: dict[str, ControlDRuleGroup] = {}
        for payload in groups_payload:
            folder_pk = str(payload.get("PK"))
            action = IntegrationManager._mapping_or_empty(payload.get("action"))
            groups[folder_pk] = ControlDRuleGroup(
                group_pk=folder_pk,
                name=IntegrationManager._require_string(payload, "group"),
                action_do=(int(action["do"]) if "do" in action else None),
            )

        rules: dict[str, ControlDRule] = {}
        for payload in rules_payload:
            rule_pk = IntegrationManager._require_string(payload, "PK")
            group_value = payload.get("group")
            group_pk: str | None = None
            if isinstance(group_value, int) and group_value != 0:
                group_pk = str(group_value)
            elif isinstance(group_value, str) and group_value and group_value != "0":
                group_pk = group_value
            identity = build_rule_identity(group_pk, rule_pk)
            action = IntegrationManager._mapping_or_empty(payload.get("action"))
            group_name = groups[group_pk].name if group_pk in groups else None
            rules[identity] = ControlDRule(
                identity=identity,
                rule_pk=rule_pk,
                order=int(payload.get("order", 0) or 0),
                group_pk=group_pk,
                group_name=group_name,
                enabled=bool(action.get("status", 0)),
                action_do=int(action.get("do", 0) or 0),
                comment=IntegrationManager._optional_string(payload.get("comment"))
                or "",
                ttl=(int(action["ttl"]) if "ttl" in action else None),
            )
        return rules

    @staticmethod
    def _normalize_rule_groups(
        groups_payload: tuple[dict[str, Any], ...],
    ) -> dict[str, ControlDRuleGroup]:
        """Normalize grouped-rule folders for entity surfaces and writes."""
        groups: dict[str, ControlDRuleGroup] = {}
        for payload in groups_payload:
            folder_pk = str(payload.get("PK"))
            action = IntegrationManager._mapping_or_empty(payload.get("action"))
            groups[folder_pk] = ControlDRuleGroup(
                group_pk=folder_pk,
                name=IntegrationManager._require_string(payload, "group"),
                enabled=bool(action.get("status", 0)) and "do" in action,
                action_do=(int(action["do"]) if "do" in action else None),
            )
        return groups

    @staticmethod
    def _normalize_profile_options(
        catalog_payload: tuple[dict[str, Any], ...],
        state_payload: tuple[dict[str, Any], ...],
    ) -> dict[str, ControlDProfileOption]:
        """Normalize profile options by joining catalog metadata to sparse state."""
        state_by_pk = {
            IntegrationManager._require_string(
                payload, "PK"
            ): IntegrationManager._normalize_option_value_key(payload.get("value"))
            for payload in state_payload
            if isinstance(payload, dict) and isinstance(payload.get("PK"), str)
        }
        options: dict[str, ControlDProfileOption] = {}
        for payload in catalog_payload:
            option_pk = IntegrationManager._require_string(payload, "PK")
            option_type = IntegrationManager._require_string(payload, "type")
            choices = IntegrationManager._normalize_option_choices(payload)
            entity_kind = "unsupported"
            if option_type == "toggle":
                entity_kind = "toggle"
            elif option_type == "dropdown" and choices:
                entity_kind = "select"
            elif option_type == "field" and option_pk in {
                "ttl_blck",
                "ttl_spff",
                "ttl_pass",
            }:
                entity_kind = "toggle"
            options[option_pk] = ControlDProfileOption(
                option_pk=option_pk,
                title=IntegrationManager._require_string(payload, "title"),
                description=IntegrationManager._optional_string(
                    payload.get("description")
                ),
                option_type=option_type,
                info_url=IntegrationManager._optional_string(payload.get("info_url")),
                current_value_key=state_by_pk.get(option_pk),
                default_value_key=IntegrationManager._normalize_option_value_key(
                    payload.get("default_value")
                ),
                choices=choices,
                entity_kind=entity_kind,
            )
        return options

    @staticmethod
    def _normalize_option_choices(
        payload: dict[str, Any],
    ) -> tuple[ControlDProfileOptionChoice, ...]:
        """Normalize selectable choices for one option payload."""
        default_value = payload.get("default_value")
        if isinstance(default_value, dict):
            return tuple(
                ControlDProfileOptionChoice(value=str(value), label=str(label))
                for value, label in default_value.items()
                if isinstance(label, str)
            )
        return ()

    @staticmethod
    def _normalize_option_value_key(value: Any) -> str | None:
        """Normalize a profile option value into a stable string key."""
        if value is None:
            return None
        if isinstance(value, bool):
            return "1" if value else None
        if isinstance(value, int | float):
            if value == 0:
                return None
            return format(value, "g")
        if isinstance(value, str):
            return value or None
        return None

    @staticmethod
    def _normalize_user(user_payload: dict[str, Any]) -> ControlDUser:
        """Normalize the user payload into the runtime identity model."""
        instance_id = IntegrationManager._require_string(user_payload, "id")
        account_pk = IntegrationManager._require_string(user_payload, "PK")
        safe_countries = tuple(
            country
            for country in user_payload.get("safe_countries", [])
            if isinstance(country, str)
        )
        return ControlDUser(
            instance_id=instance_id,
            account_pk=account_pk,
            last_active=IntegrationManager._optional_string(
                user_payload.get("last_active")
            ),
            stats_endpoint=IntegrationManager._optional_string(
                user_payload.get("stats_endpoint")
            ),
            status=IntegrationManager._optional_string(user_payload.get("status")),
            safe_countries=safe_countries,
        )

    @staticmethod
    def _require_string(payload: dict[str, Any], key: str) -> str:
        """Return a required payload field as a string."""
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Payload is missing required string field {key!r}")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Return an optional string value."""
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _mapping_or_empty(value: Any) -> dict[str, Any]:
        """Return a mapping value or an empty mapping."""
        return value if isinstance(value, dict) else {}
