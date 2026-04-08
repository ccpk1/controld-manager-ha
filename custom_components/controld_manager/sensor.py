"""Sensor platform for Control D Manager."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ACCOUNT_STATUS,
    ATTR_ANALYTICS_END_TIME,
    ATTR_ANALYTICS_START_TIME,
    ATTR_CONSECUTIVE_FAILED_REFRESHES,
    ATTR_DISCOVERED_ENDPOINT_COUNT,
    ATTR_LAST_REFRESH_ATTEMPT,
    ATTR_LAST_REFRESH_ERROR,
    ATTR_LAST_REFRESH_TRIGGER,
    ATTR_LAST_SUCCESSFUL_REFRESH,
    ATTR_PAUSED_UNTIL,
    ATTR_REFRESH_IN_PROGRESS,
    ATTR_ROUTER_CLIENT_COUNT,
    ATTR_STATS_ENDPOINT,
    PURPOSE_INSTANCE_ANALYTICS,
    PURPOSE_INSTANCE_STATUS,
    PURPOSE_INSTANCE_SUMMARY,
    PURPOSE_PROFILE_ANALYTICS,
    PURPOSE_PROFILE_STATUS,
    PURPOSE_PROFILE_SUMMARY,
    TRANS_KEY_ENTITY_BYPASSED_QUERIES,
    TRANS_KEY_ENTITY_PIHOLE_BLOCKED_QUERIES,
    TRANS_KEY_ENTITY_PIHOLE_BLOCKED_QUERIES_RATIO,
    TRANS_KEY_ENTITY_PIHOLE_TOTAL_QUERIES,
    TRANS_KEY_ENTITY_PIHOLE_UNIQUE_CLIENTS,
    TRANS_KEY_ENTITY_PROFILE_COUNT,
    TRANS_KEY_ENTITY_REDIRECTED_QUERIES,
    TRANS_KEY_ENTITY_STATUS,
)
from .entity import ControlDManagerInstanceEntity, ControlDManagerProfileEntity
from .models import (
    ControlDAccountAnalytics,
    ControlDManagerRuntime,
    ControlDSyncStatus,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[ControlDManagerRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Control D sensors for one config entry."""
    runtime = config_entry.runtime_data
    runtime.managers.entity.register_platform(
        "sensor",
        async_add_entities,
        lambda key: _build_sensor_entity(config_entry, key),
    )
    await runtime.managers.entity.async_sync_platform("sensor")

    @callback
    def _async_handle_coordinator_update() -> None:
        hass.async_create_task(runtime.managers.entity.async_sync_platform("sensor"))

    config_entry.async_on_unload(
        runtime.active_coordinator.async_add_listener(_async_handle_coordinator_update)
    )


def _build_sensor_entity(
    config_entry: ConfigEntry[ControlDManagerRuntime], key: str
) -> SensorEntity:
    """Build one sensor entity from the entity-manager key."""
    if key.startswith("profile::"):
        scope, profile_pk, sensor_key = key.split("::", 2)
        del scope
        if sensor_key == "total_queries":
            return ControlDManagerProfileTotalQueriesSensor(config_entry, profile_pk)
        if sensor_key == "blocked_queries":
            return ControlDManagerProfileBlockedQueriesSensor(config_entry, profile_pk)
        if sensor_key == "status":
            return ControlDManagerProfileStatusSensor(config_entry, profile_pk)
        if sensor_key == "endpoint_count":
            return ControlDManagerProfileEndpointCountSensor(config_entry, profile_pk)
        if sensor_key == "blocked_queries_ratio":
            return ControlDManagerProfileBlockedQueriesRatioSensor(
                config_entry, profile_pk
            )
        if sensor_key == "bypassed_queries":
            return ControlDManagerProfileBypassedQueriesSensor(config_entry, profile_pk)
        if sensor_key == "redirected_queries":
            return ControlDManagerProfileRedirectedQueriesSensor(
                config_entry, profile_pk
            )
        raise ValueError(f"Unsupported Control D profile sensor key {key!r}")

    if key == "instance::profile_count":
        return ControlDManagerProfileCountSensor(config_entry)
    if key == "instance::endpoint_count":
        return ControlDManagerEndpointCountSensor(config_entry)
    if key == "instance::status":
        return ControlDManagerStatusSensor(config_entry)
    if key == "instance::total_queries":
        return ControlDManagerTotalQueriesSensor(config_entry)
    if key == "instance::blocked_queries":
        return ControlDManagerBlockedQueriesSensor(config_entry)
    if key == "instance::bypassed_queries":
        return ControlDManagerBypassedQueriesSensor(config_entry)
    if key == "instance::redirected_queries":
        return ControlDManagerRedirectedQueriesSensor(config_entry)
    if key == "instance::blocked_queries_ratio":
        return ControlDManagerBlockedQueriesRatioSensor(config_entry)
    raise ValueError(f"Unsupported Control D sensor key {key!r}")


def _runtime_health(sync_status: ControlDSyncStatus) -> str:
    """Return the current runtime health derived from refresh state."""
    if sync_status.last_refresh_error is None:
        return "healthy"
    if (
        sync_status.consecutive_failed_refreshes == 1
        and sync_status.last_successful_refresh is not None
    ):
        return "degraded"
    return "problem"


def _format_compact_duration(duration: timedelta) -> str:
    """Return a compact rounded-up duration label."""
    total_minutes = max(1, int((duration.total_seconds() + 59) // 60))
    days, remainder_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder_minutes, 60)

    if days:
        return f"{days}d{hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h{minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def _disabled_status_label(paused_until: datetime, now: datetime) -> str:
    """Return the compact disabled status label for a paused profile."""
    return f"Disabled: {_format_compact_duration(paused_until - now)}"


def _status_attributes(runtime: ControlDManagerRuntime) -> dict[str, object]:
    """Return refresh metadata shared by status sensors."""
    attributes: dict[str, object] = {}
    user = runtime.registry.user
    sync_status = runtime.sync_status
    attributes.update(
        {
            ATTR_LAST_REFRESH_ATTEMPT: sync_status.last_refresh_attempt,
            ATTR_LAST_SUCCESSFUL_REFRESH: sync_status.last_successful_refresh,
            ATTR_REFRESH_IN_PROGRESS: sync_status.refresh_in_progress,
            ATTR_LAST_REFRESH_TRIGGER: sync_status.last_refresh_trigger,
            ATTR_CONSECUTIVE_FAILED_REFRESHES: (
                sync_status.consecutive_failed_refreshes
            ),
        }
    )
    if user is not None and user.stats_endpoint is not None:
        attributes[ATTR_STATS_ENDPOINT] = user.stats_endpoint
    if user is not None and user.status is not None:
        attributes[ATTR_ACCOUNT_STATUS] = user.status
    if sync_status.last_refresh_error is not None:
        attributes[ATTR_LAST_REFRESH_ERROR] = sync_status.last_refresh_error
    return attributes


class ControlDManagerStatusSensor(ControlDManagerInstanceEntity, SensorEntity):
    """Expose the current account and polling status."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = TRANS_KEY_ENTITY_STATUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _purpose = PURPOSE_INSTANCE_STATUS

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the account-status sensor."""
        super().__init__(config_entry, "status")
        self._attr_name = "Status"
        self._attr_options = ["healthy", "degraded", "problem"]

    @property
    def available(self) -> bool:
        """Keep the status sensor visible even when the last poll failed."""
        return True

    @property
    def native_value(self) -> str:
        """Return the current health of the Control D integration runtime."""
        return _runtime_health(self.runtime.sync_status)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return concise account and refresh metadata."""
        attributes = super().extra_state_attributes or {}
        attributes.update(_status_attributes(self.runtime))
        return attributes


class ControlDManagerProfileStatusSensor(ControlDManagerProfileEntity, SensorEntity):
    """Expose the current profile and polling status."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = TRANS_KEY_ENTITY_STATUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _purpose = PURPOSE_PROFILE_STATUS

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize the profile-status sensor."""
        super().__init__(config_entry, profile_pk, "status")
        self._attr_name = "Status"

    @property
    def options(self) -> list[str]:
        """Return the allowed profile status states."""
        base_options = ["healthy", "degraded", "problem", "disabled"]
        if (disabled_label := self._disabled_label()) is None:
            return base_options
        return [*base_options, disabled_label]

    @property
    def available(self) -> bool:
        """Keep the profile status visible while the profile exists."""
        return self.profile is not None

    @property
    def native_value(self) -> str:
        """Return the current health of the profile surface."""
        if (disabled_label := self._disabled_label()) is not None:
            return disabled_label
        return _runtime_health(self.runtime.sync_status)

    @property
    def icon(self) -> str:
        """Return an icon matching the current profile status."""
        if self._disabled_label() is not None:
            return "mdi:pause-circle"
        match _runtime_health(self.runtime.sync_status):
            case "degraded":
                return "mdi:shield-alert"
            case "problem":
                return "mdi:shield-off"
            case _:
                return "mdi:shield-check"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return profile status metadata."""
        attributes = super().extra_state_attributes or {}
        attributes.update(_status_attributes(self.runtime))
        if (profile := self.profile) is not None and profile.paused_until is not None:
            attributes[ATTR_PAUSED_UNTIL] = profile.paused_until.isoformat()
        return attributes

    def _disabled_label(self) -> str | None:
        """Return the current compact disabled label when the profile is paused."""
        if (profile := self.profile) is None or profile.paused_until is None:
            return None
        now = dt_util.utcnow().astimezone(UTC)
        if profile.paused_until <= now:
            return None
        return _disabled_status_label(profile.paused_until, now)


class ControlDManagerProfileCountSensor(ControlDManagerInstanceEntity, SensorEntity):
    """Expose the current number of discovered profiles."""

    _attr_translation_key = TRANS_KEY_ENTITY_PROFILE_COUNT
    _attr_native_unit_of_measurement = "profiles"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _purpose = PURPOSE_INSTANCE_SUMMARY

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the profile-count sensor."""
        super().__init__(config_entry, "profile_count")
        self._attr_name = "Profile count"

    @property
    def native_value(self) -> int:
        """Return the current number of discovered profiles."""
        return len(self.runtime.registry.profiles)


class ControlDManagerEndpointCountSensor(ControlDManagerInstanceEntity, SensorEntity):
    """Expose the current number of discovered endpoints."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_UNIQUE_CLIENTS
    _attr_native_unit_of_measurement = "endpoints"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _purpose = PURPOSE_INSTANCE_SUMMARY

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the endpoint-count sensor."""
        super().__init__(config_entry, "endpoint_count")
        self._attr_name = "Endpoint count"

    @property
    def native_value(self) -> int:
        """Return the current number of discovered endpoints."""
        return self.runtime.registry.endpoint_inventory.protected_endpoint_count

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return the explicit and nested endpoint counts."""
        attributes = super().extra_state_attributes or {}
        attributes.update(
            {
                ATTR_DISCOVERED_ENDPOINT_COUNT: (
                    self.runtime.registry.endpoint_inventory.discovered_endpoint_count
                ),
                ATTR_ROUTER_CLIENT_COUNT: (
                    self.runtime.registry.endpoint_inventory.router_client_count
                ),
            }
        )
        return attributes


class ControlDManagerProfileEndpointCountSensor(
    ControlDManagerProfileEntity, SensorEntity
):
    """Expose the current number of endpoints attached to one profile."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_UNIQUE_CLIENTS
    _attr_native_unit_of_measurement = "endpoints"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _purpose = PURPOSE_PROFILE_SUMMARY

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize the profile endpoint-count sensor."""
        super().__init__(config_entry, profile_pk, "endpoint_count")
        self._attr_name = "Endpoint count"

    @property
    def native_value(self) -> int:
        """Return the current number of endpoints attached to this profile."""
        return self.runtime.registry.protected_endpoint_count_for_profile(
            self._profile_pk
        )


class ControlDManagerAccountAnalyticsSensor(
    ControlDManagerInstanceEntity, SensorEntity
):
    """Base sensor for account-level analytics summary values."""

    _purpose = PURPOSE_INSTANCE_ANALYTICS
    _attr_native_unit_of_measurement = "queries"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """Return whether analytics data is currently available."""
        return super().available and self.runtime.registry.account_analytics is not None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return the analytics reporting window when available."""
        attributes = super().extra_state_attributes or {}
        analytics = self.runtime.registry.account_analytics
        if analytics is None:
            return attributes
        if analytics.start_time is not None:
            attributes[ATTR_ANALYTICS_START_TIME] = analytics.start_time
        if analytics.end_time is not None:
            attributes[ATTR_ANALYTICS_END_TIME] = analytics.end_time
        return attributes


class ControlDManagerTotalQueriesSensor(ControlDManagerAccountAnalyticsSensor):
    """Expose the current account-level total query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_TOTAL_QUERIES

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the total-queries sensor."""
        super().__init__(config_entry, "total_queries")
        self._attr_name = "Total queries"
        self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> int | None:
        """Return the current total query count for the reporting window."""
        analytics = self.runtime.registry.account_analytics
        if analytics is None:
            return None
        return analytics.total_queries


class ControlDManagerBlockedQueriesSensor(ControlDManagerAccountAnalyticsSensor):
    """Expose the current account-level blocked query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_BLOCKED_QUERIES

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the blocked-queries sensor."""
        super().__init__(config_entry, "blocked_queries")
        self._attr_name = "Blocked queries"
        self._attr_suggested_display_precision = 0

    @property
    def available(self) -> bool:
        """Return whether a proven blocked-query total is available."""
        analytics = self.runtime.registry.account_analytics
        return (
            super().available
            and analytics is not None
            and analytics.blocked_queries is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the current blocked query count for the reporting window."""
        analytics = self.runtime.registry.account_analytics
        if analytics is None or analytics.blocked_queries is None:
            return None
        return analytics.blocked_queries


class ControlDManagerBypassedQueriesSensor(ControlDManagerAccountAnalyticsSensor):
    """Expose the current account-level bypassed query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_BYPASSED_QUERIES

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the bypassed-queries sensor."""
        super().__init__(config_entry, "bypassed_queries")
        self._attr_name = "Bypassed queries"
        self._attr_suggested_display_precision = 0

    @property
    def available(self) -> bool:
        """Return whether a proven bypassed-query total is available."""
        analytics = self.runtime.registry.account_analytics
        return (
            super().available
            and analytics is not None
            and analytics.bypassed_queries is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the current bypassed query count for the reporting window."""
        analytics = self.runtime.registry.account_analytics
        if analytics is None or analytics.bypassed_queries is None:
            return None
        return analytics.bypassed_queries


class ControlDManagerRedirectedQueriesSensor(ControlDManagerAccountAnalyticsSensor):
    """Expose the current account-level redirected query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_REDIRECTED_QUERIES

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the redirected-queries sensor."""
        super().__init__(config_entry, "redirected_queries")
        self._attr_name = "Redirected queries"
        self._attr_suggested_display_precision = 0

    @property
    def available(self) -> bool:
        """Return whether a proven redirected-query total is available."""
        analytics = self.runtime.registry.account_analytics
        return (
            super().available
            and analytics is not None
            and analytics.redirected_queries is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the current redirected query count for the reporting window."""
        analytics = self.runtime.registry.account_analytics
        if analytics is None or analytics.redirected_queries is None:
            return None
        return analytics.redirected_queries


class ControlDManagerBlockedQueriesRatioSensor(ControlDManagerAccountAnalyticsSensor):
    """Expose the current blocked-query ratio for the account."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_BLOCKED_QUERIES_RATIO
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, config_entry: ConfigEntry[ControlDManagerRuntime]) -> None:
        """Initialize the blocked-query-ratio sensor."""
        super().__init__(config_entry, "blocked_queries_ratio")
        self._attr_name = "Blocked queries ratio"
        self._attr_suggested_display_precision = 1

    @property
    def available(self) -> bool:
        """Return whether a proven blocked-query ratio is available."""
        analytics = self.runtime.registry.account_analytics
        return (
            super().available
            and analytics is not None
            and analytics.blocked_queries_ratio is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the current blocked-query ratio for the reporting window."""
        analytics = self.runtime.registry.account_analytics
        if analytics is None or analytics.blocked_queries_ratio is None:
            return None
        return round(analytics.blocked_queries_ratio, 1)


class ControlDManagerProfileAnalyticsSensor(ControlDManagerProfileEntity, SensorEntity):
    """Base sensor for profile-level analytics summary values."""

    _purpose = PURPOSE_PROFILE_ANALYTICS
    _attr_native_unit_of_measurement = "queries"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def analytics(self) -> ControlDAccountAnalytics | None:
        """Return the current analytics snapshot for this profile."""
        return self.runtime.registry.profile_analytics_by_profile.get(self._profile_pk)

    @property
    def available(self) -> bool:
        """Return whether analytics data is currently available."""
        return super().available and self.analytics is not None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return the analytics reporting window when available."""
        attributes = super().extra_state_attributes or {}
        if (analytics := self.analytics) is None:
            return attributes
        if analytics.start_time is not None:
            attributes[ATTR_ANALYTICS_START_TIME] = analytics.start_time
        if analytics.end_time is not None:
            attributes[ATTR_ANALYTICS_END_TIME] = analytics.end_time
        return attributes


class ControlDManagerProfileTotalQueriesSensor(ControlDManagerProfileAnalyticsSensor):
    """Expose the current profile-level total query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_TOTAL_QUERIES

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize the profile total-queries sensor."""
        super().__init__(config_entry, profile_pk, "total_queries")
        self._attr_name = "Total queries"
        self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> int | None:
        """Return the current total query count for the reporting window."""
        if (analytics := self.analytics) is None:
            return None
        return analytics.total_queries


class ControlDManagerProfileBlockedQueriesSensor(ControlDManagerProfileAnalyticsSensor):
    """Expose the current profile-level blocked query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_BLOCKED_QUERIES

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize the profile blocked-queries sensor."""
        super().__init__(config_entry, profile_pk, "blocked_queries")
        self._attr_name = "Blocked queries"
        self._attr_suggested_display_precision = 0

    @property
    def available(self) -> bool:
        """Return whether a proven blocked-query total is available."""
        analytics = self.analytics
        return (
            super().available
            and analytics is not None
            and analytics.blocked_queries is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the current blocked query count for the reporting window."""
        if (analytics := self.analytics) is None or analytics.blocked_queries is None:
            return None
        return analytics.blocked_queries


class ControlDManagerProfileBlockedQueriesRatioSensor(
    ControlDManagerProfileAnalyticsSensor
):
    """Expose the current blocked-query ratio for the profile."""

    _attr_translation_key = TRANS_KEY_ENTITY_PIHOLE_BLOCKED_QUERIES_RATIO
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize the profile blocked-query-ratio sensor."""
        super().__init__(config_entry, profile_pk, "blocked_queries_ratio")
        self._attr_name = "Blocked queries ratio"
        self._attr_suggested_display_precision = 1

    @property
    def available(self) -> bool:
        """Return whether a proven blocked-query ratio is available."""
        analytics = self.analytics
        return (
            super().available
            and analytics is not None
            and analytics.blocked_queries_ratio is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the current blocked-query ratio for the reporting window."""
        if (
            analytics := self.analytics
        ) is None or analytics.blocked_queries_ratio is None:
            return None
        return round(analytics.blocked_queries_ratio, 1)


class ControlDManagerProfileBypassedQueriesSensor(
    ControlDManagerProfileAnalyticsSensor
):
    """Expose the current profile-level bypassed query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_BYPASSED_QUERIES

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize the profile bypassed-queries sensor."""
        super().__init__(config_entry, profile_pk, "bypassed_queries")
        self._attr_name = "Bypassed queries"
        self._attr_suggested_display_precision = 0

    @property
    def available(self) -> bool:
        """Return whether a proven bypassed-query total is available."""
        analytics = self.analytics
        return (
            super().available
            and analytics is not None
            and analytics.bypassed_queries is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the current bypassed query count for the reporting window."""
        if (analytics := self.analytics) is None or analytics.bypassed_queries is None:
            return None
        return analytics.bypassed_queries


class ControlDManagerProfileRedirectedQueriesSensor(
    ControlDManagerProfileAnalyticsSensor
):
    """Expose the current profile-level redirected query count."""

    _attr_translation_key = TRANS_KEY_ENTITY_REDIRECTED_QUERIES

    def __init__(
        self,
        config_entry: ConfigEntry[ControlDManagerRuntime],
        profile_pk: str,
    ) -> None:
        """Initialize the profile redirected-queries sensor."""
        super().__init__(config_entry, profile_pk, "redirected_queries")
        self._attr_name = "Redirected queries"
        self._attr_suggested_display_precision = 0

    @property
    def available(self) -> bool:
        """Return whether a proven redirected-query total is available."""
        analytics = self.analytics
        return (
            super().available
            and analytics is not None
            and analytics.redirected_queries is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the current redirected query count for the reporting window."""
        if (
            analytics := self.analytics
        ) is None or analytics.redirected_queries is None:
            return None
        return analytics.redirected_queries
