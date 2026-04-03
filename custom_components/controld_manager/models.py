"""Typed models for Control D Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Self

from .const import (
    CONF_ALLOWED_SERVICE_CATEGORIES,
    CONF_AUTO_ENABLE_SERVICE_SWITCHES,
    CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES,
    CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES,
    CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    CONF_ENDPOINT_SENSORS_ENABLED,
    CONF_EXPOSED_CUSTOM_RULES,
    CONF_MANAGED_IN_HOME_ASSISTANT,
    CONF_PROFILE_ANALYTICS_INTERVAL_MINUTES,
    CONF_PROFILE_POLICIES,
    DEFAULT_CONFIGURATION_SYNC_INTERVAL,
    DEFAULT_ENDPOINT_ANALYTICS_INTERVAL,
    DEFAULT_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    DEFAULT_PROFILE_ANALYTICS_INTERVAL,
    MAX_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    MAX_REFRESH_INTERVAL,
    MIN_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    MIN_REFRESH_INTERVAL,
)

if TYPE_CHECKING:
    from .api import ControlDAPIClient
    from .coordinator import ControlDManagerDataUpdateCoordinator
    from .managers import (
        DeviceManager,
        EndpointManager,
        EntityManager,
        IntegrationManager,
        ProfileManager,
    )


@dataclass(slots=True, frozen=True)
class ControlDUser:
    """Normalized Control D instance identity and metadata."""

    instance_id: str
    account_pk: str
    display_name: str | None = None
    last_active: str | None = None
    stats_endpoint: str | None = None
    status: str | None = None
    safe_countries: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class ControlDAttachedProfile:
    """A normalized attached-profile reference from a device payload."""

    profile_pk: str
    name: str | None = None


@dataclass(slots=True, frozen=True)
class ControlDProfileSummary:
    """Normalized summary model for a Control D profile."""

    profile_pk: str
    name: str
    paused_until: datetime | None = None


@dataclass(slots=True, frozen=True)
class ControlDEndpointSummary:
    """Normalized summary model for a Control D endpoint."""

    device_id: str
    endpoint_pk: str | None
    name: str | None
    owning_profile_pk: str | None
    last_active: datetime | None = None
    attached_profiles: tuple[ControlDAttachedProfile, ...] = ()
    parent_device_id: str | None = None


@dataclass(slots=True, frozen=True)
class ControlDFilterLevel:
    """One available mode level for a Control D filter."""

    slug: str
    title: str
    enabled: bool


@dataclass(slots=True, frozen=True)
class ControlDFilter:
    """Normalized filter state for one profile."""

    filter_pk: str
    name: str
    enabled: bool
    action_do: int
    selected_level_slug: str | None = None
    levels: tuple[ControlDFilterLevel, ...] = ()

    @property
    def supports_modes(self) -> bool:
        """Return whether the filter exposes a selectable mode list."""
        return len(self.levels) > 1

    @property
    def effective_level_slug(self) -> str | None:
        """Return the best available level slug for reads and enable writes."""
        if self.selected_level_slug is not None:
            return self.selected_level_slug
        for level in self.levels:
            if level.enabled:
                return level.slug
        if self.levels:
            return self.levels[0].slug
        return None

    @property
    def effective_level_title(self) -> str | None:
        """Return the best available level title for the current filter state."""
        if (level_slug := self.effective_level_slug) is None:
            return None
        for level in self.levels:
            if level.slug == level_slug:
                return level.title
        return None


@dataclass(slots=True, frozen=True)
class ControlDServiceCategory:
    """Normalized service category metadata."""

    category_pk: str
    name: str
    description: str | None = None
    count: int = 0


@dataclass(slots=True, frozen=True)
class ControlDService:
    """Normalized service state for one profile."""

    service_pk: str
    name: str
    category_pk: str
    category_name: str
    enabled: bool
    action_do: int
    warning: str | None = None
    unlock_location: str | None = None

    @property
    def current_mode(self) -> str:
        """Return the current service mode for Home Assistant controls."""
        if not self.enabled:
            return "Off"
        return service_mode_from_action_do(self.action_do)


@dataclass(slots=True, frozen=True)
class ControlDRuleGroup:
    """Normalized grouped-rule folder metadata."""

    group_pk: str
    name: str
    action_do: int | None = None


def build_rule_identity(group_pk: str | None, rule_pk: str) -> str:
    """Build a stable persisted identity for a rule selection."""
    if group_pk is None:
        return f"root|{rule_pk}"
    return f"group:{group_pk}|{rule_pk}"


def build_rule_group_target(group_pk: str) -> str:
    """Build a stored target value for a rule folder selection."""
    return f"group:{group_pk}"


def build_rule_item_target(rule_identity: str) -> str:
    """Build a stored target value for a single rule selection."""
    return f"rule:{rule_identity}"


@dataclass(slots=True, frozen=True)
class ControlDRule:
    """Normalized rule state for one profile."""

    identity: str
    rule_pk: str
    order: int
    group_pk: str | None
    group_name: str | None
    enabled: bool
    action_do: int
    ttl: int | None = None


@dataclass(slots=True, frozen=True)
class ControlDProfilePolicy:
    """Compact stored policy for one Control D profile."""

    managed_in_home_assistant: bool = True
    endpoint_sensors_enabled: bool = False
    endpoint_inactivity_threshold_minutes: int = (
        DEFAULT_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES
    )
    allowed_service_categories: frozenset[str] = frozenset()
    auto_enable_service_switches: bool = False
    exposed_custom_rules: frozenset[str] = frozenset()

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> Self:
        """Build a typed profile policy from stored entry options."""
        if not isinstance(data, dict):
            return cls()

        threshold = data.get(CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES)
        if not isinstance(threshold, int):
            threshold = DEFAULT_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES
        threshold = max(
            MIN_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
            min(MAX_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES, threshold),
        )

        return cls(
            managed_in_home_assistant=bool(
                data.get(CONF_MANAGED_IN_HOME_ASSISTANT, True)
            ),
            endpoint_sensors_enabled=bool(
                data.get(CONF_ENDPOINT_SENSORS_ENABLED, False)
            ),
            endpoint_inactivity_threshold_minutes=threshold,
            allowed_service_categories=frozenset(
                item
                for item in data.get(CONF_ALLOWED_SERVICE_CATEGORIES, [])
                if isinstance(item, str) and item
            ),
            auto_enable_service_switches=bool(
                data.get(CONF_AUTO_ENABLE_SERVICE_SWITCHES, False)
            ),
            exposed_custom_rules=frozenset(
                item
                for item in data.get(CONF_EXPOSED_CUSTOM_RULES, [])
                if isinstance(item, str) and item
            ),
        )

    def as_mapping(self) -> dict[str, Any]:
        """Serialize the policy into config-entry options storage."""
        return {
            CONF_MANAGED_IN_HOME_ASSISTANT: self.managed_in_home_assistant,
            CONF_ENDPOINT_SENSORS_ENABLED: self.endpoint_sensors_enabled,
            CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES: (
                self.endpoint_inactivity_threshold_minutes
            ),
            CONF_ALLOWED_SERVICE_CATEGORIES: sorted(self.allowed_service_categories),
            CONF_AUTO_ENABLE_SERVICE_SWITCHES: self.auto_enable_service_switches,
            CONF_EXPOSED_CUSTOM_RULES: sorted(self.exposed_custom_rules),
        }

    def exposed_rule_identities(
        self, rules_by_identity: dict[str, ControlDRule]
    ) -> set[str]:
        """Resolve stored folder and rule targets into concrete rule identities."""
        resolved: set[str] = set()
        for target in self.exposed_custom_rules:
            if target.startswith("group:") and not target.startswith("group:group:"):
                group_pk = target.removeprefix("group:")
                resolved.update(
                    rule.identity
                    for rule in rules_by_identity.values()
                    if rule.group_pk == group_pk
                )
                continue
            if target.startswith("rule:"):
                rule_identity = target.removeprefix("rule:")
                if rule_identity in rules_by_identity:
                    resolved.add(rule_identity)
        return resolved


@dataclass(slots=True, frozen=True)
class ControlDOptions:
    """Typed options contract for one config entry."""

    configuration_sync_interval: timedelta = DEFAULT_CONFIGURATION_SYNC_INTERVAL
    profile_analytics_interval: timedelta = DEFAULT_PROFILE_ANALYTICS_INTERVAL
    endpoint_analytics_interval: timedelta = DEFAULT_ENDPOINT_ANALYTICS_INTERVAL
    profile_policies: dict[str, ControlDProfilePolicy] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> Self:
        """Build typed options from raw config-entry options."""
        if not isinstance(data, dict):
            return cls()

        return cls(
            configuration_sync_interval=_bounded_timedelta(
                data.get(CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES),
                DEFAULT_CONFIGURATION_SYNC_INTERVAL,
            ),
            profile_analytics_interval=_bounded_timedelta(
                data.get(CONF_PROFILE_ANALYTICS_INTERVAL_MINUTES),
                DEFAULT_PROFILE_ANALYTICS_INTERVAL,
            ),
            endpoint_analytics_interval=_bounded_timedelta(
                data.get(CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES),
                DEFAULT_ENDPOINT_ANALYTICS_INTERVAL,
            ),
            profile_policies={
                profile_pk: ControlDProfilePolicy.from_mapping(policy)
                for profile_pk, policy in data.get(CONF_PROFILE_POLICIES, {}).items()
                if isinstance(profile_pk, str)
            },
        )

    def as_mapping(self) -> dict[str, Any]:
        """Serialize options into config-entry storage."""
        return {
            CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES: int(
                self.configuration_sync_interval.total_seconds() // 60
            ),
            CONF_PROFILE_ANALYTICS_INTERVAL_MINUTES: int(
                self.profile_analytics_interval.total_seconds() // 60
            ),
            CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES: int(
                self.endpoint_analytics_interval.total_seconds() // 60
            ),
            CONF_PROFILE_POLICIES: {
                profile_pk: policy.as_mapping()
                for profile_pk, policy in self.profile_policies.items()
            },
        }

    def profile_policy(self, profile_pk: str) -> ControlDProfilePolicy:
        """Return the effective policy for one discovered profile."""
        return self.profile_policies.get(profile_pk, ControlDProfilePolicy())

    def included_profile_pks(self, profile_pks: set[str]) -> set[str]:
        """Return the currently included profile identifiers."""
        return {
            profile_pk
            for profile_pk in profile_pks
            if self.profile_policy(profile_pk).managed_in_home_assistant
        }


def _bounded_timedelta(value: Any, default: timedelta) -> timedelta:
    """Normalize a minute count into the allowed refresh interval bounds."""
    minutes = int(default.total_seconds() // 60)
    if isinstance(value, int):
        minutes = value
    min_minutes = int(MIN_REFRESH_INTERVAL.total_seconds() // 60)
    max_minutes = int(MAX_REFRESH_INTERVAL.total_seconds() // 60)
    minutes = max(min_minutes, min(max_minutes, minutes))
    return timedelta(minutes=minutes)


@dataclass(slots=True, frozen=True)
class ControlDProfileDetailPayload:
    """Raw detail payloads for one profile."""

    filters: tuple[dict[str, Any], ...] = ()
    services: tuple[dict[str, Any], ...] = ()
    groups: tuple[dict[str, Any], ...] = ()
    rules: tuple[dict[str, Any], ...] = ()


@dataclass(slots=True, frozen=True)
class ControlDInventoryPayload:
    """Raw inventory payloads after endpoint-specific envelope normalization."""

    user: dict[str, Any]
    profiles: tuple[dict[str, Any], ...]
    devices: tuple[dict[str, Any], ...]
    profile_details: dict[str, ControlDProfileDetailPayload] = field(
        default_factory=dict
    )
    service_categories: tuple[dict[str, Any], ...] = ()
    service_catalog: tuple[dict[str, Any], ...] = ()


def _build_endpoint_inventory_stats() -> ControlDEndpointInventoryStats:
    """Build a default endpoint inventory stats instance."""
    return ControlDEndpointInventoryStats()


@dataclass(slots=True, frozen=True)
class ControlDRegistry:
    """Coordinator-owned normalized snapshot for one config entry."""

    user: ControlDUser | None = None
    endpoint_inventory: ControlDEndpointInventoryStats = field(
        default_factory=_build_endpoint_inventory_stats
    )
    profiles: dict[str, ControlDProfileSummary] = field(default_factory=dict)
    endpoints: dict[str, ControlDEndpointSummary] = field(default_factory=dict)
    filters_by_profile: dict[str, dict[str, ControlDFilter]] = field(
        default_factory=dict
    )
    services_by_profile: dict[str, dict[str, ControlDService]] = field(
        default_factory=dict
    )
    rules_by_profile: dict[str, dict[str, ControlDRule]] = field(default_factory=dict)
    service_categories: dict[str, ControlDServiceCategory] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Self:
        """Return an empty runtime registry."""
        return cls()


@dataclass(slots=True, frozen=True)
class ControlDRefreshIntervals:
    """Bounded refresh-group intervals for one runtime."""

    configuration_sync: timedelta
    profile_analytics: timedelta
    endpoint_analytics: timedelta


@dataclass(slots=True, frozen=True)
class ControlDEndpointInventoryStats:
    """Derived account-level endpoint inventory counts."""

    discovered_endpoint_count: int = 0
    router_client_count: int = 0
    protected_endpoint_count: int = 0


def service_mode_from_action_do(action_do: int) -> str:
    """Translate a Control D service action code into a UI mode label."""
    return {
        0: "Blocked",
        1: "Bypassed",
        2: "Redirected",
    }.get(action_do, "Bypassed")


def service_mode_options() -> tuple[str, ...]:
    """Return the supported Home Assistant service-mode options."""
    return ("Off", "Blocked", "Bypassed", "Redirected")


@dataclass(slots=True)
class ControlDSyncStatus:
    """Live refresh metadata kept in runtime memory."""

    last_refresh_attempt: datetime | None = None
    last_successful_refresh: datetime | None = None
    last_refresh_error: str | None = None
    last_refresh_trigger: str | None = None
    consecutive_failed_refreshes: int = 0
    refresh_in_progress: bool = False


@dataclass(slots=True)
class ControlDManagerSet:
    """All manager instances owned by one runtime."""

    integration: IntegrationManager
    device: DeviceManager
    entity: EntityManager
    profile: ProfileManager
    endpoint: EndpointManager

    def attach_runtime(self, runtime: ControlDManagerRuntime) -> None:
        """Attach the shared runtime reference to every manager."""
        self.integration.attach_runtime(runtime)
        self.device.attach_runtime(runtime)
        self.entity.attach_runtime(runtime)
        self.profile.attach_runtime(runtime)
        self.endpoint.attach_runtime(runtime)


@dataclass(slots=True)
class ControlDManagerRuntime:
    """Entry-scoped runtime stored in ConfigEntry.runtime_data."""

    entry_id: str
    instance_id: str
    client: ControlDAPIClient
    options: ControlDOptions
    refresh_intervals: ControlDRefreshIntervals
    registry: ControlDRegistry
    managers: ControlDManagerSet
    sync_status: ControlDSyncStatus = field(default_factory=ControlDSyncStatus)
    coordinator: ControlDManagerDataUpdateCoordinator | None = None

    @property
    def active_coordinator(self) -> ControlDManagerDataUpdateCoordinator:
        """Return the active coordinator once setup has attached it."""
        if self.coordinator is None:
            raise RuntimeError("Control D runtime coordinator is not attached")
        return self.coordinator
