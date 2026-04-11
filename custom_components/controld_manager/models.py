"""Typed models for Control D Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Self

from .const import (
    CONF_ADVANCED_PROFILE_OPTIONS,
    CONF_ALLOWED_SERVICE_CATEGORIES,
    CONF_AUTO_ENABLE_SERVICE_SWITCHES,
    CONF_CONFIGURATION_SYNC_INTERVAL_MINUTES,
    CONF_ENDPOINT_ANALYTICS_INTERVAL_MINUTES,
    CONF_ENDPOINT_INACTIVITY_THRESHOLD_MINUTES,
    CONF_ENDPOINT_SENSORS_ENABLED,
    CONF_EXPOSE_EXTERNAL_FILTERS,
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
    RULE_ACTION_BLOCK,
    RULE_ACTION_BYPASS,
    RULE_ACTION_OFF,
    RULE_ACTION_REDIRECT,
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


SERVICE_MODE_OFF = "off"
SERVICE_MODE_BLOCKED = "blocked"
SERVICE_MODE_BYPASSED = "bypassed"
SERVICE_MODE_REDIRECTED = "redirected"

SERVICE_MODE_LABELS: dict[str, str] = {
    SERVICE_MODE_OFF: "Off",
    SERVICE_MODE_BLOCKED: "Blocked",
    SERVICE_MODE_BYPASSED: "Bypassed",
    SERVICE_MODE_REDIRECTED: "Redirected",
}

DEFAULT_RULE_MODE_BLOCKING = "blocking"
DEFAULT_RULE_MODE_BYPASSING = "bypassing"
DEFAULT_RULE_MODE_REDIRECTING = "redirecting"

DEFAULT_RULE_MODE_LABELS: dict[str, str] = {
    DEFAULT_RULE_MODE_BLOCKING: "Blocking",
    DEFAULT_RULE_MODE_BYPASSING: "Bypassing",
    DEFAULT_RULE_MODE_REDIRECTING: "Redirecting",
}

ENDPOINT_ANALYTICS_NONE = "none"
ENDPOINT_ANALYTICS_SOME = "some"
ENDPOINT_ANALYTICS_FULL = "full"

ENDPOINT_ANALYTICS_MODE_LABELS: dict[str, str] = {
    ENDPOINT_ANALYTICS_NONE: "None",
    ENDPOINT_ANALYTICS_SOME: "Some",
    ENDPOINT_ANALYTICS_FULL: "Full",
}


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
class ControlDAccountAnalytics:
    """Normalized account-level analytics for one reporting window."""

    total_queries: int
    blocked_queries: int | None = None
    bypassed_queries: int | None = None
    redirected_queries: int | None = None
    blocked_queries_ratio: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


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
    associated_client_count: int = 0
    parent_device_id: str | None = None


def build_client_alias_target_key(
    parent_endpoint_device_id: str, client_id: str
) -> str:
    """Build a stable in-memory key for one client alias target."""
    return f"client|{parent_endpoint_device_id}|{client_id}"


@dataclass(slots=True, frozen=True)
class ControlDClientAliasTarget:
    """Normalized client-scoped target metadata for alias mutations."""

    target_key: str
    source_kind: str
    endpoint_device_id: str | None
    endpoint_pk: str | None
    endpoint_name: str | None
    owning_profile_pk: str | None
    parent_endpoint_device_id: str
    parent_endpoint_name: str | None
    client_id: str
    client_alias: str | None = None
    client_hostname: str | None = None
    client_ip_address: str | None = None
    client_mac_address: str | None = None

    @property
    def display_name(self) -> str:
        """Return the best available user-facing label for the target."""
        return (
            self.client_alias
            or self.endpoint_name
            or self.client_hostname
            or self.client_mac_address
            or self.parent_endpoint_name
            or self.endpoint_device_id
            or self.parent_endpoint_device_id
        )


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
    external: bool = False
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
    via: str | None = None
    via_v6: str | None = None
    warning: str | None = None
    unlock_location: str | None = None

    @property
    def current_mode(self) -> str:
        """Return the current service mode for Home Assistant controls."""
        if not self.enabled:
            return SERVICE_MODE_OFF
        return service_mode_from_action_do(self.action_do)

    @property
    def redirect_target(self) -> str | None:
        """Return the active redirect target when one is available."""
        if self.action_do not in {2, 3}:
            return None
        if self.via is not None and self.via != "-1":
            return self.via
        if self.via_v6 is not None and self.via_v6 != "-1":
            return self.via_v6
        return None

    @property
    def redirect_target_type(self) -> str | None:
        """Return the upstream redirect target family when available."""
        if self.action_do == 3:
            if self.via == "LOCAL":
                return "auto"
            if self.via == "?":
                return "random"
            return "location"
        if self.action_do == 2:
            return "proxy"
        return None


@dataclass(slots=True, frozen=True)
class ControlDRuleGroup:
    """Normalized grouped-rule folder metadata."""

    group_pk: str
    name: str
    enabled: bool = False
    action_do: int | None = None

    @property
    def current_mode(self) -> str:
        """Return the current folder-rule mode key."""
        return rule_group_mode_from_action(self.action_do, self.enabled)


@dataclass(slots=True, frozen=True)
class ControlDProfileOptionChoice:
    """One selectable value for a profile option."""

    value: str
    label: str


@dataclass(slots=True, frozen=True)
class ControlDProfileOption:
    """Normalized profile option state for one profile."""

    option_pk: str
    title: str
    description: str | None
    option_type: str
    info_url: str | None
    current_value_key: str | None = None
    default_value_key: str | None = None
    choices: tuple[ControlDProfileOptionChoice, ...] = ()
    entity_kind: str = "unsupported"

    @property
    def is_enabled(self) -> bool:
        """Return whether the option is currently enabled."""
        return self.current_value_key is not None

    @property
    def current_select_option(self) -> str:
        """Return the current label for a select-style option."""
        if self.current_value_key is None:
            return "Off"
        for choice in self.choices:
            if choice.value == self.current_value_key:
                return choice.label
        return "Off"

    @property
    def select_options(self) -> tuple[str, ...]:
        """Return the UI options for a select-style option."""
        return ("Off", *(choice.label for choice in self.choices))

    def choice_value_for_label(self, label: str) -> str | None:
        """Return the upstream value for one select label."""
        if label == "Off":
            return None
        for choice in self.choices:
            if choice.label == label:
                return choice.value
        return None

    def choice_value_for_input(self, candidate: str) -> str | None:
        """Return the upstream value for one label or raw upstream value."""
        if candidate == "Off":
            return None
        for choice in self.choices:
            if choice.label == candidate or choice.value == candidate:
                return choice.value
        return None


@dataclass(slots=True, frozen=True)
class ControlDDefaultRule:
    """Normalized default-rule state for one profile."""

    enabled: bool
    action_do: int
    via: str | None = None

    @property
    def current_mode(self) -> str:
        """Return the current default-rule mode label."""
        return default_rule_mode_from_action(self.action_do, self.enabled, self.via)


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
    comment: str = ""
    ttl: int | None = None

    @property
    def action_key(self) -> str:
        """Return the current rule action key."""
        return rule_action_key_from_action_do(self.action_do)


@dataclass(slots=True, frozen=True)
class ControlDProfilePolicy:
    """Compact stored policy for one Control D profile."""

    managed_in_home_assistant: bool = True
    expose_external_filters: bool = False
    advanced_profile_options: bool = False
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
            expose_external_filters=bool(data.get(CONF_EXPOSE_EXTERNAL_FILTERS, False)),
            advanced_profile_options=bool(
                data.get(CONF_ADVANCED_PROFILE_OPTIONS, False)
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
            CONF_EXPOSE_EXTERNAL_FILTERS: self.expose_external_filters,
            CONF_ADVANCED_PROFILE_OPTIONS: self.advanced_profile_options,
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
        """Resolve stored explicit rule targets into concrete rule identities."""
        resolved: set[str] = set()
        for target in self.exposed_custom_rules:
            if target.startswith("rule:"):
                rule_identity = target.removeprefix("rule:")
                if rule_identity in rules_by_identity:
                    resolved.add(rule_identity)
        return resolved

    def exposed_rule_group_pks(
        self, groups_by_pk: dict[str, ControlDRuleGroup]
    ) -> set[str]:
        """Resolve stored folder targets into concrete folder identifiers."""
        return {
            group_pk
            for target in self.exposed_custom_rules
            if target.startswith("group:") and not target.startswith("group:group:")
            if (group_pk := target.removeprefix("group:")) in groups_by_pk
        }


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
    external_filters: tuple[dict[str, Any], ...] = ()
    options: tuple[dict[str, Any], ...] = ()
    default_rule: dict[str, Any] | None = None
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
    option_catalog: tuple[dict[str, Any], ...] = ()
    service_categories: tuple[dict[str, Any], ...] = ()
    service_catalog: tuple[dict[str, Any], ...] = ()
    account_analytics: ControlDAccountAnalytics | None = None
    analytics_clients_by_endpoint: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )


def _build_endpoint_inventory_stats() -> ControlDEndpointInventoryStats:
    """Build a default endpoint inventory stats instance."""
    return ControlDEndpointInventoryStats()


@dataclass(slots=True, frozen=True)
class ControlDRegistry:
    """Coordinator-owned normalized snapshot for one config entry."""

    user: ControlDUser | None = None
    account_analytics: ControlDAccountAnalytics | None = None
    profile_analytics_by_profile: dict[str, ControlDAccountAnalytics] = field(
        default_factory=dict
    )
    endpoint_inventory: ControlDEndpointInventoryStats = field(
        default_factory=_build_endpoint_inventory_stats
    )
    profiles: dict[str, ControlDProfileSummary] = field(default_factory=dict)
    endpoints: dict[str, ControlDEndpointSummary] = field(default_factory=dict)
    client_alias_targets: dict[str, ControlDClientAliasTarget] = field(
        default_factory=dict
    )
    filters_by_profile: dict[str, dict[str, ControlDFilter]] = field(
        default_factory=dict
    )
    default_rules_by_profile: dict[str, ControlDDefaultRule] = field(
        default_factory=dict
    )
    rule_groups_by_profile: dict[str, dict[str, ControlDRuleGroup]] = field(
        default_factory=dict
    )
    services_by_profile: dict[str, dict[str, ControlDService]] = field(
        default_factory=dict
    )
    rules_by_profile: dict[str, dict[str, ControlDRule]] = field(default_factory=dict)
    options_by_profile: dict[str, dict[str, ControlDProfileOption]] = field(
        default_factory=dict
    )
    service_categories: dict[str, ControlDServiceCategory] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Self:
        """Return an empty runtime registry."""
        return cls()

    def protected_endpoint_count_for_profile(self, profile_pk: str) -> int:
        """Return the protected endpoint count for one profile."""
        return sum(
            1 + endpoint.associated_client_count
            for endpoint in self.endpoints.values()
            if any(
                attached_profile.profile_pk == profile_pk
                for attached_profile in endpoint.attached_profiles
            )
        )


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
    """Translate a Control D service action code into a stable mode key."""
    return {
        0: SERVICE_MODE_BLOCKED,
        1: SERVICE_MODE_BYPASSED,
        2: SERVICE_MODE_REDIRECTED,
        3: SERVICE_MODE_REDIRECTED,
    }.get(action_do, SERVICE_MODE_BYPASSED)


def service_mode_options() -> tuple[str, ...]:
    """Return the supported entity state keys for service-mode selects."""
    return (
        SERVICE_MODE_OFF,
        SERVICE_MODE_BLOCKED,
        SERVICE_MODE_BYPASSED,
        SERVICE_MODE_REDIRECTED,
    )


def service_mode_labels() -> tuple[str, ...]:
    """Return the supported service-call labels for service modes."""
    return tuple(SERVICE_MODE_LABELS[mode] for mode in service_mode_options())


def normalize_service_mode(mode: str) -> str:
    """Normalize a service mode label or key into a stable key."""
    normalized = mode.strip().lower()
    if normalized in SERVICE_MODE_LABELS:
        return normalized

    label_map = {label.lower(): key for key, label in SERVICE_MODE_LABELS.items()}
    return label_map[normalized]


def rule_action_key_from_action_do(action_do: int) -> str:
    """Translate a Control D rule action code into a stable key."""
    return {
        0: RULE_ACTION_BLOCK,
        1: RULE_ACTION_BYPASS,
        2: RULE_ACTION_REDIRECT,
        3: RULE_ACTION_REDIRECT,
    }.get(action_do, RULE_ACTION_BYPASS)


def rule_action_label_from_action_do(action_do: int) -> str:
    """Translate a Control D rule action code into an English label."""
    return {
        0: "Block",
        1: "Bypass",
        2: "Redirect",
        3: "Redirect",
    }.get(action_do, "Bypass")


def default_rule_mode_from_action(
    action_do: int, enabled: bool, via: str | None
) -> str:
    """Translate a Control D default-rule action into a stable mode key."""
    del enabled, via
    return {
        0: DEFAULT_RULE_MODE_BLOCKING,
        1: DEFAULT_RULE_MODE_BYPASSING,
        3: DEFAULT_RULE_MODE_REDIRECTING,
    }.get(action_do, DEFAULT_RULE_MODE_BLOCKING)


def default_rule_action_from_mode(mode: str) -> tuple[int, str | None]:
    """Translate a mode label or key into the Control D default-rule payload."""
    normalized = normalize_default_rule_mode(mode)
    return {
        DEFAULT_RULE_MODE_BLOCKING: (0, None),
        DEFAULT_RULE_MODE_BYPASSING: (1, None),
        DEFAULT_RULE_MODE_REDIRECTING: (3, "LOCAL"),
    }[normalized]


def default_rule_mode_options() -> tuple[str, ...]:
    """Return the supported entity state keys for default-rule selects."""
    return (
        DEFAULT_RULE_MODE_BLOCKING,
        DEFAULT_RULE_MODE_BYPASSING,
        DEFAULT_RULE_MODE_REDIRECTING,
    )


def default_rule_mode_labels() -> tuple[str, ...]:
    """Return the supported service-call labels for default-rule modes."""
    return tuple(DEFAULT_RULE_MODE_LABELS[mode] for mode in default_rule_mode_options())


def normalize_default_rule_mode(mode: str) -> str:
    """Normalize a default-rule mode label or key into a stable key."""
    normalized = mode.strip().lower()
    if normalized in DEFAULT_RULE_MODE_LABELS:
        return normalized

    label_map = {label.lower(): key for key, label in DEFAULT_RULE_MODE_LABELS.items()}
    return label_map[normalized]


def endpoint_analytics_logging_mode_options() -> tuple[str, ...]:
    """Return the supported endpoint analytics logging mode keys."""
    return (
        ENDPOINT_ANALYTICS_NONE,
        ENDPOINT_ANALYTICS_SOME,
        ENDPOINT_ANALYTICS_FULL,
    )


def endpoint_analytics_logging_mode_labels() -> tuple[str, ...]:
    """Return the supported service-call labels for endpoint analytics logging."""
    return tuple(
        ENDPOINT_ANALYTICS_MODE_LABELS[mode]
        for mode in endpoint_analytics_logging_mode_options()
    )


def normalize_endpoint_analytics_logging_mode(mode: str) -> str:
    """Normalize an endpoint analytics logging label or key into a stable key."""
    normalized = mode.strip().lower()
    if normalized in ENDPOINT_ANALYTICS_MODE_LABELS:
        return normalized

    label_map = {
        label.lower(): key for key, label in ENDPOINT_ANALYTICS_MODE_LABELS.items()
    }
    return label_map[normalized]


def endpoint_analytics_stats_value_from_mode(mode: str) -> int:
    """Translate one endpoint analytics logging mode into the upstream stats value."""
    normalized = normalize_endpoint_analytics_logging_mode(mode)
    return {
        ENDPOINT_ANALYTICS_NONE: 0,
        ENDPOINT_ANALYTICS_SOME: 1,
        ENDPOINT_ANALYTICS_FULL: 2,
    }[normalized]


def rule_group_mode_from_action(action_do: int | None, enabled: bool) -> str:
    """Translate a folder action into a stable mode key."""
    if not enabled or action_do is None or action_do < 0:
        return RULE_ACTION_OFF
    return {
        0: RULE_ACTION_BLOCK,
        1: RULE_ACTION_BYPASS,
        2: RULE_ACTION_REDIRECT,
        3: RULE_ACTION_REDIRECT,
    }.get(action_do, RULE_ACTION_OFF)


def rule_group_action_from_mode(mode: str) -> tuple[bool, int]:
    """Translate a folder-rule mode key into the Control D payload model."""
    return {
        RULE_ACTION_OFF: (True, -1),
        RULE_ACTION_BLOCK: (True, 0),
        RULE_ACTION_BYPASS: (True, 1),
        RULE_ACTION_REDIRECT: (True, 2),
    }[mode]


def rule_group_mode_options() -> tuple[str, ...]:
    """Return the supported Home Assistant folder-rule option keys."""
    return (
        RULE_ACTION_OFF,
        RULE_ACTION_BLOCK,
        RULE_ACTION_BYPASS,
        RULE_ACTION_REDIRECT,
    )


def rule_action_do_from_key(action_key: str) -> int:
    """Translate a rule action key into the Control D write payload value."""
    return {
        RULE_ACTION_BLOCK: 0,
        RULE_ACTION_BYPASS: 1,
        RULE_ACTION_REDIRECT: 2,
    }[action_key]


def rule_action_options() -> tuple[str, ...]:
    """Return the supported mutable rule action keys."""
    return (
        RULE_ACTION_BLOCK,
        RULE_ACTION_BYPASS,
        RULE_ACTION_REDIRECT,
    )


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
