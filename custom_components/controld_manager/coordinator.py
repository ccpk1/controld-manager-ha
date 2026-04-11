"""Coordinator runtime for Control D Manager."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ControlDApiAuthError,
    ControlDApiConnectionError,
    ControlDApiResponseError,
)
from .const import DOMAIN
from .models import ControlDInventoryPayload, ControlDManagerRuntime, ControlDRegistry

LOGGER = logging.getLogger(__name__)


class ControlDManagerDataUpdateCoordinator(DataUpdateCoordinator[ControlDRegistry]):
    """Coordinator-owned inventory refresh path for one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry[ControlDManagerRuntime],
        runtime: ControlDManagerRuntime,
    ) -> None:
        """Initialize the runtime coordinator."""
        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=runtime.refresh_intervals.configuration_sync,
            config_entry=entry,
        )
        self._runtime = runtime
        self._refresh_trigger = "scheduled"
        self._unavailable_logged = False

    def _raise_update_failure(
        self,
        message: str,
        err: Exception,
        *,
        auth_failed: bool = False,
    ) -> ControlDRegistry:
        """Record one refresh failure and raise the Home Assistant-facing error."""
        sync_status = self._runtime.sync_status
        sync_status.last_refresh_error = message
        sync_status.consecutive_failed_refreshes += 1
        if not self.last_update_success:
            self.async_update_listeners()

        if not auth_failed and not self._unavailable_logged:
            LOGGER.info("The API is unavailable: %s", message)
            self._unavailable_logged = True

        if auth_failed:
            raise ConfigEntryAuthFailed(message) from err
        raise UpdateFailed(message) from err

    async def async_run_manual_refresh(self) -> None:
        """Run an on-demand refresh and label it as manual."""
        previous_trigger = self._refresh_trigger
        self._refresh_trigger = "manual"
        try:
            await self.async_refresh()
        finally:
            self._refresh_trigger = previous_trigger

    async def _async_refresh_analytics(
        self, registry: ControlDRegistry
    ) -> ControlDRegistry:
        """Refresh account and profile analytics for the current registry."""
        user = registry.user
        if user is None or user.stats_endpoint is None:
            return registry

        local_now = dt_util.now()
        start_time = dt_util.as_utc(local_now - timedelta(days=1))
        end_time = dt_util.as_utc(local_now)
        included_profile_pks = sorted(
            self._runtime.options.included_profile_pks(set(registry.profiles))
        )

        try:
            results = await asyncio.gather(
                self._runtime.client.async_get_account_analytics(
                    user.stats_endpoint,
                    start_time=start_time,
                    end_time=end_time,
                ),
                *(
                    self._runtime.client.async_get_profile_analytics(
                        user.stats_endpoint,
                        profile_pk,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    for profile_pk in included_profile_pks
                ),
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
            ValueError,
        ) as err:
            LOGGER.debug("Unable to refresh Control D analytics: %s", err)
            return replace(
                registry,
                account_analytics=self._runtime.registry.account_analytics,
                profile_analytics_by_profile=(
                    self._runtime.registry.profile_analytics_by_profile
                ),
            )

        account_analytics = results[0]
        profile_analytics_by_profile = dict(
            zip(included_profile_pks, results[1:], strict=True)
        )
        return replace(
            registry,
            account_analytics=account_analytics,
            profile_analytics_by_profile=profile_analytics_by_profile,
        )

    async def _async_fetch_analytics_clients_by_endpoint(
        self,
        inventory: ControlDInventoryPayload,
    ) -> dict[str, dict[str, Any]]:
        """Fetch analytics client payloads for aliasable parent endpoints."""
        stats_endpoint = self._runtime.client.extract_stats_endpoint(inventory.user)
        if stats_endpoint is None:
            return {}

        parent_endpoint_ids = sorted(
            self._runtime.managers.endpoint.aliasable_parent_endpoint_ids(
                inventory.devices
            )
        )
        if not parent_endpoint_ids:
            return {}

        try:
            results = await asyncio.gather(
                *(
                    self._runtime.client.async_get_analytics_clients(
                        stats_endpoint,
                        endpoint_id=parent_endpoint_id,
                    )
                    for parent_endpoint_id in parent_endpoint_ids
                )
            )
        except (
            ControlDApiAuthError,
            ControlDApiConnectionError,
            ControlDApiResponseError,
            ValueError,
        ) as err:
            LOGGER.debug("Unable to refresh Control D analytics clients: %s", err)
            return {}

        analytics_clients_by_endpoint: dict[str, dict[str, Any]] = {}
        for result in results:
            analytics_clients_by_endpoint.update(result)
        return analytics_clients_by_endpoint

    async def _async_update_data(self) -> ControlDRegistry:
        """Fetch and normalize the current Control D inventory snapshot."""
        sync_status = self._runtime.sync_status
        sync_status.last_refresh_attempt = datetime.now(UTC)
        sync_status.last_refresh_trigger = self._refresh_trigger
        sync_status.refresh_in_progress = True
        try:
            inventory = await self._runtime.client.async_get_inventory()
            included_profile_pks = self._runtime.options.included_profile_pks(
                {profile["PK"] for profile in inventory.profiles if "PK" in profile}
            )
            needs_service_catalog = any(
                self._runtime.options.profile_policy(
                    profile_pk
                ).allowed_service_categories
                for profile_pk in included_profile_pks
            )
            if included_profile_pks:
                option_catalog_task = (
                    self._runtime.client.async_get_profile_option_catalog()
                )
                detail_results = await asyncio.gather(
                    option_catalog_task,
                    *(
                        self._runtime.client.async_get_profile_detail(
                            profile_pk,
                            include_services=bool(
                                self._runtime.options.profile_policy(
                                    profile_pk
                                ).allowed_service_categories
                            ),
                            include_rules=bool(
                                self._runtime.options.profile_policy(
                                    profile_pk
                                ).exposed_custom_rules
                            ),
                        )
                        for profile_pk in sorted(included_profile_pks)
                    ),
                )
                option_catalog = detail_results[0]
                profile_detail_results = detail_results[1:]
                inventory = ControlDInventoryPayload(
                    user=inventory.user,
                    profiles=inventory.profiles,
                    devices=inventory.devices,
                    profile_details=dict(
                        zip(
                            sorted(included_profile_pks),
                            profile_detail_results,
                            strict=True,
                        )
                    ),
                    option_catalog=tuple(option_catalog),
                    service_categories=tuple(
                        await (
                            self._runtime.client.async_get_service_categories()
                            if needs_service_catalog
                            else asyncio.sleep(0, result=[])
                        )
                    ),
                    service_catalog=tuple(
                        await (
                            self._runtime.client.async_get_service_catalog()
                            if needs_service_catalog
                            else asyncio.sleep(0, result=[])
                        )
                    ),
                )
            inventory = replace(
                inventory,
                analytics_clients_by_endpoint=(
                    await self._async_fetch_analytics_clients_by_endpoint(inventory)
                ),
            )
            registry = self._runtime.managers.integration.build_registry(inventory)
        except ControlDApiAuthError as err:
            return self._raise_update_failure(
                "Control D authentication failed",
                err,
                auth_failed=True,
            )
        except ControlDApiConnectionError as err:
            return self._raise_update_failure(
                "Unable to reach the Control D API",
                err,
            )
        except ControlDApiResponseError as err:
            return self._raise_update_failure(
                "Unexpected response from the Control D API",
                err,
            )
        except ValueError as err:
            return self._raise_update_failure(
                "Control D inventory normalization failed",
                err,
            )
        finally:
            sync_status.refresh_in_progress = False

        registry = await self._async_refresh_analytics(registry)

        self._runtime.registry = registry
        if self._unavailable_logged:
            LOGGER.info("The API is back online")
            self._unavailable_logged = False
        sync_status.last_successful_refresh = datetime.now(UTC)
        sync_status.last_refresh_error = None
        sync_status.consecutive_failed_refreshes = 0
        return registry
