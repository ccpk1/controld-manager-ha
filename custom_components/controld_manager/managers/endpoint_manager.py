"""Endpoint normalization and orchestration for Control D."""

from __future__ import annotations

import asyncio
import ipaddress
import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from ..models import (
    ControlDAttachedProfile,
    ControlDClientAliasTarget,
    ControlDEndpointInventoryStats,
    ControlDEndpointSummary,
    build_client_alias_target_key,
)
from .base_manager import BaseManager

PROFILE_KEY_PATTERN = re.compile(r"^profile\d*$")


class EndpointManager(BaseManager):
    """Own endpoint normalization and endpoint-to-profile mapping."""

    async def async_set_endpoint_analytics_logging(
        self,
        endpoints: tuple[ControlDEndpointSummary, ...],
        stats: int,
    ) -> None:
        """Update analytics logging across one or more resolved endpoints."""
        await asyncio.gather(
            *(
                self.runtime.client.async_set_endpoint_analytics_logging(
                    endpoint.device_id,
                    stats=stats,
                )
                for endpoint in endpoints
            )
        )
        await self.runtime.active_coordinator.async_refresh()

    async def async_rename_endpoints(
        self,
        endpoints: tuple[ControlDEndpointSummary, ...],
        name: str,
    ) -> None:
        """Rename one or more resolved endpoints and refresh runtime state."""
        await asyncio.gather(
            *(
                self.runtime.client.async_rename_endpoint(
                    endpoint.device_id,
                    name=name,
                )
                for endpoint in endpoints
            )
        )
        for endpoint in endpoints:
            self._update_cached_endpoint_name(endpoint, name=name)
        await self.runtime.active_coordinator.async_refresh()

    async def async_set_client_aliases(
        self,
        targets: tuple[ControlDClientAliasTarget, ...],
        alias: str,
    ) -> None:
        """Set one alias across one or more resolved client targets."""
        stats_endpoint = self._require_stats_endpoint()
        await asyncio.gather(
            *(
                self.runtime.client.async_set_endpoint_alias(
                    stats_endpoint,
                    device_id=target.parent_endpoint_device_id,
                    client_id=target.client_id,
                    alias=alias,
                )
                for target in targets
            )
        )
        for target in targets:
            self._update_cached_client_alias_target(target, alias=alias)
        await self.runtime.active_coordinator.async_refresh()

    async def async_clear_client_aliases(
        self,
        targets: tuple[ControlDClientAliasTarget, ...],
    ) -> None:
        """Clear one alias across one or more resolved client targets."""
        stats_endpoint = self._require_stats_endpoint()
        await asyncio.gather(
            *(
                self.runtime.client.async_clear_endpoint_alias(
                    stats_endpoint,
                    device_id=target.parent_endpoint_device_id,
                    client_id=target.client_id,
                )
                for target in targets
            )
        )
        for target in targets:
            self._update_cached_client_alias_target(target, alias=None)
        await self.runtime.active_coordinator.async_refresh()

    def normalize_client_alias_targets(
        self,
        devices_payload: tuple[dict[str, Any], ...],
        endpoints: dict[str, ControlDEndpointSummary],
        analytics_clients_by_endpoint: dict[str, dict[str, Any]],
    ) -> dict[str, ControlDClientAliasTarget]:
        """Normalize client-scoped alias targets from devices and analytics data."""
        targets: dict[str, ControlDClientAliasTarget] = {}

        for device_payload in devices_payload:
            if not (relationship := self._extract_client_relationship(device_payload)):
                continue

            endpoint_device_id, parent_endpoint_device_id, client_id = relationship
            endpoint_row = endpoints.get(endpoint_device_id)
            parent_endpoint_row = endpoints.get(parent_endpoint_device_id)
            analytics_client_payload = self._analytics_client_payload(
                analytics_clients_by_endpoint,
                parent_endpoint_device_id,
                client_id,
            )
            target_key = build_client_alias_target_key(
                parent_endpoint_device_id,
                client_id,
            )

            targets[target_key] = ControlDClientAliasTarget(
                target_key=target_key,
                source_kind="client",
                endpoint_device_id=endpoint_device_id,
                endpoint_pk=(endpoint_row.endpoint_pk if endpoint_row else None),
                endpoint_name=(endpoint_row.name if endpoint_row else None),
                owning_profile_pk=(
                    endpoint_row.owning_profile_pk if endpoint_row else None
                ),
                parent_endpoint_device_id=parent_endpoint_device_id,
                parent_endpoint_name=(
                    parent_endpoint_row.name if parent_endpoint_row else None
                ),
                client_id=client_id,
                client_alias=self._optional_string(
                    analytics_client_payload.get("alias")
                ),
                client_hostname=self._optional_string(
                    analytics_client_payload.get("host")
                ),
                client_ip_address=self._optional_string(
                    analytics_client_payload.get("ip")
                ),
                client_mac_address=self._optional_string(
                    analytics_client_payload.get("mac")
                ),
            )

        for (
            parent_endpoint_device_id,
            client_id,
            analytics_client_payload,
        ) in self._iter_analytics_clients(analytics_clients_by_endpoint):
            target_key = build_client_alias_target_key(
                parent_endpoint_device_id,
                client_id,
            )
            if target_key in targets:
                continue

            parent_endpoint_row = endpoints.get(parent_endpoint_device_id)
            targets[target_key] = ControlDClientAliasTarget(
                target_key=target_key,
                source_kind="analytics_client",
                endpoint_device_id=None,
                endpoint_pk=None,
                endpoint_name=self._optional_string(
                    analytics_client_payload.get("alias")
                ),
                owning_profile_pk=None,
                parent_endpoint_device_id=parent_endpoint_device_id,
                parent_endpoint_name=(
                    parent_endpoint_row.name if parent_endpoint_row else None
                ),
                client_id=client_id,
                client_alias=self._optional_string(
                    analytics_client_payload.get("alias")
                ),
                client_hostname=self._optional_string(
                    analytics_client_payload.get("host")
                ),
                client_ip_address=self._optional_string(
                    analytics_client_payload.get("ip")
                ),
                client_mac_address=self._optional_string(
                    analytics_client_payload.get("mac")
                ),
            )

        return targets

    def aliasable_parent_endpoint_ids(
        self, devices_payload: tuple[dict[str, Any], ...]
    ) -> set[str]:
        """Return parent endpoint IDs that expose aliasable client relationships."""
        explicit_parent_ids = {
            parent_endpoint_device_id
            for device_payload in devices_payload
            if (relationship := self._extract_client_relationship(device_payload))
            for _, parent_endpoint_device_id, _ in (relationship,)
        }

        analytics_parent_ids = {
            device_id
            for device_payload in devices_payload
            if (device_id := self._optional_string(device_payload.get("device_id")))
            is not None
            and bool(self._iter_nested_clients(device_payload))
        }

        return explicit_parent_ids | analytics_parent_ids

    def resolve_client_alias_target(
        self,
        *,
        endpoint_mac: str | None = None,
        endpoint_name: str | None = None,
        endpoint_hostname: str | None = None,
        endpoint_ip: str | None = None,
        parent_endpoint_name: str | None = None,
    ) -> ControlDClientAliasTarget:
        """Resolve exactly one client alias target from runtime data."""
        targets = tuple(self.runtime.registry.client_alias_targets.values())
        if parent_endpoint_name is not None:
            normalized_parent_name = self._normalize_name(parent_endpoint_name)
            targets = tuple(
                target
                for target in targets
                if target.parent_endpoint_name is not None
                and self._normalize_name(target.parent_endpoint_name)
                == normalized_parent_name
            )

        selectors: tuple[tuple[str | None, str], ...] = (
            (endpoint_mac, "mac"),
            (endpoint_name, "name"),
            (endpoint_hostname, "hostname"),
            (endpoint_ip, "ip"),
        )
        for selector_value, selector_kind in selectors:
            if selector_value is None:
                continue
            matches = tuple(
                target
                for target in targets
                if self._matches_client_alias_target(
                    target,
                    selector_kind=selector_kind,
                    selector_value=selector_value,
                )
            )
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError(
                    f"Ambiguous client alias target for selector {selector_kind!r}"
                )
            raise ValueError(
                f"Unknown client alias target for selector {selector_kind!r}"
            )

        raise ValueError("Provide one client alias target selector")

    def resolve_endpoint_target(
        self,
        *,
        endpoint_name: str,
    ) -> ControlDEndpointSummary:
        """Resolve exactly one endpoint row from endpoint-scoped runtime data."""
        normalized_name = self._normalize_name(endpoint_name)
        matches = tuple(
            endpoint
            for endpoint in self.runtime.registry.endpoints.values()
            if endpoint.name is not None
            and self._normalize_name(endpoint.name) == normalized_name
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError("Ambiguous endpoint target for selector 'name'")
        raise ValueError("Unknown endpoint target for selector 'name'")

    def _update_cached_client_alias_target(
        self,
        target: ControlDClientAliasTarget,
        *,
        alias: str | None,
    ) -> None:
        """Update one cached client alias target after a successful write."""
        self.runtime.registry.client_alias_targets[target.target_key] = replace(
            target,
            client_alias=alias,
        )

    def _update_cached_endpoint_name(
        self,
        endpoint: ControlDEndpointSummary,
        *,
        name: str,
    ) -> None:
        """Update cached endpoint-facing names after a successful rename."""
        self.runtime.registry.endpoints[endpoint.device_id] = replace(
            endpoint,
            name=name,
        )
        for target_key, target in tuple(
            self.runtime.registry.client_alias_targets.items()
        ):
            if target.endpoint_device_id == endpoint.device_id:
                self.runtime.registry.client_alias_targets[target_key] = replace(
                    target,
                    endpoint_name=name,
                )
            elif target.parent_endpoint_device_id == endpoint.device_id:
                self.runtime.registry.client_alias_targets[target_key] = replace(
                    target,
                    parent_endpoint_name=name,
                )

    def _require_stats_endpoint(self) -> str:
        """Return the configured stats endpoint or raise a configuration error."""
        user = self.runtime.registry.user
        if user is None or user.stats_endpoint is None:
            raise ValueError("The Control D stats endpoint is unavailable")
        return user.stats_endpoint

    def normalize_endpoints(
        self, devices_payload: tuple[dict[str, Any], ...]
    ) -> dict[str, ControlDEndpointSummary]:
        """Normalize endpoint inventory into immutable endpoint summaries."""
        router_client_counts_by_parent = self._summarize_router_clients(devices_payload)
        endpoints: dict[str, ControlDEndpointSummary] = {}
        for device_payload in devices_payload:
            device_id = self._require_string(device_payload, "device_id")
            attached_profiles = tuple(self._iter_attached_profiles(device_payload))
            owning_profile_pk = (
                attached_profiles[0].profile_pk if attached_profiles else None
            )
            endpoints[device_id] = ControlDEndpointSummary(
                device_id=device_id,
                endpoint_pk=self._optional_string(device_payload.get("PK")),
                name=self._optional_string(device_payload.get("name")),
                owning_profile_pk=owning_profile_pk,
                last_active=self._normalize_datetime_value(
                    device_payload.get("last_activity")
                    or device_payload.get("last_active")
                ),
                attached_profiles=attached_profiles,
                associated_client_count=router_client_counts_by_parent.get(
                    device_id, 0
                ),
                parent_device_id=self._extract_parent_device_id(device_payload),
            )
        return endpoints

    def summarize_inventory(
        self,
        devices_payload: tuple[dict[str, Any], ...],
        endpoints: dict[str, ControlDEndpointSummary],
    ) -> ControlDEndpointInventoryStats:
        """Return account-level endpoint totals without creating extra entities."""
        del devices_payload
        router_client_count = sum(
            endpoint.associated_client_count for endpoint in endpoints.values()
        )

        discovered_endpoint_count = len(endpoints)
        return ControlDEndpointInventoryStats(
            discovered_endpoint_count=discovered_endpoint_count,
            router_client_count=router_client_count,
            protected_endpoint_count=discovered_endpoint_count + router_client_count,
        )

    def _summarize_router_clients(
        self, devices_payload: tuple[dict[str, Any], ...]
    ) -> dict[str, int]:
        """Return deduped nested router-client counts keyed by parent device."""
        explicit_child_names_by_parent: dict[str, set[str]] = {}
        for device_payload in devices_payload:
            if (
                parent_device_id := self._extract_parent_device_id(device_payload)
            ) is None:
                continue
            if (name := self._optional_string(device_payload.get("name"))) is None:
                continue
            explicit_child_names_by_parent.setdefault(parent_device_id, set()).add(
                self._normalize_client_identity(name)
            )

        router_client_counts_by_parent: dict[str, int] = {}
        seen_client_keys: set[tuple[str, str]] = set()
        for device_payload in devices_payload:
            parent_device_id = self._optional_string(device_payload.get("device_id"))
            if parent_device_id is None:
                continue
            for client_key, client_payload in self._iter_nested_clients(device_payload):
                identity = self._client_identity(client_key, client_payload)
                if identity is None:
                    continue
                dedupe_key = (parent_device_id, identity)
                if dedupe_key in seen_client_keys:
                    continue
                seen_client_keys.add(dedupe_key)
                if identity in explicit_child_names_by_parent.get(
                    parent_device_id, set()
                ):
                    continue
                router_client_counts_by_parent[parent_device_id] = (
                    router_client_counts_by_parent.get(parent_device_id, 0) + 1
                )

        return router_client_counts_by_parent

    def _iter_attached_profiles(
        self, device_payload: dict[str, Any]
    ) -> list[ControlDAttachedProfile]:
        """Return attached profiles in upstream payload order."""
        attached_profiles: list[ControlDAttachedProfile] = []
        for key, value in device_payload.items():
            if PROFILE_KEY_PATTERN.fullmatch(key) is None or not isinstance(
                value, dict
            ):
                continue
            profile_pk = self._optional_string(value.get("PK"))
            if profile_pk is None:
                continue
            attached_profiles.append(
                ControlDAttachedProfile(
                    profile_pk=profile_pk,
                    name=self._optional_string(value.get("name")),
                )
            )
        return attached_profiles

    def _extract_parent_device_id(self, device_payload: dict[str, Any]) -> str | None:
        """Extract an optional parent device identifier from the payload."""
        parent_device = device_payload.get("parent_device")
        if isinstance(parent_device, dict):
            return self._optional_string(parent_device.get("device_id"))
        return self._optional_string(parent_device)

    def _extract_client_relationship(
        self, device_payload: dict[str, Any]
    ) -> tuple[str, str, str] | None:
        """Extract one explicit client-to-parent relationship when present."""
        endpoint_device_id = self._optional_string(device_payload.get("device_id"))
        parent_device = device_payload.get("parent_device")
        if endpoint_device_id is None or not isinstance(parent_device, dict):
            return None
        parent_endpoint_device_id = self._optional_string(
            parent_device.get("device_id")
        )
        client_id = self._optional_string(parent_device.get("client_id"))
        if parent_endpoint_device_id is None or client_id is None:
            return None
        return endpoint_device_id, parent_endpoint_device_id, client_id

    @staticmethod
    def _analytics_client_payload(
        analytics_clients_by_endpoint: dict[str, dict[str, Any]],
        parent_endpoint_device_id: str,
        client_id: str,
    ) -> dict[str, Any]:
        """Return one analytics client payload when present."""
        parent_payload = analytics_clients_by_endpoint.get(parent_endpoint_device_id)
        if not isinstance(parent_payload, dict):
            return {}
        clients_payload = parent_payload.get("clients")
        if not isinstance(clients_payload, dict):
            return {}
        client_payload = clients_payload.get(client_id)
        return client_payload if isinstance(client_payload, dict) else {}

    @staticmethod
    def _iter_analytics_clients(
        analytics_clients_by_endpoint: dict[str, dict[str, Any]],
    ) -> list[tuple[str, str, dict[str, Any]]]:
        """Iterate normalized analytics client rows keyed by parent endpoint."""
        clients: list[tuple[str, str, dict[str, Any]]] = []
        for (
            parent_endpoint_device_id,
            parent_payload,
        ) in analytics_clients_by_endpoint.items():
            if not isinstance(parent_payload, dict):
                continue
            clients_payload = parent_payload.get("clients")
            if not isinstance(clients_payload, dict):
                continue
            for client_id, client_payload in clients_payload.items():
                if not isinstance(client_payload, dict):
                    continue
                clients.append((parent_endpoint_device_id, client_id, client_payload))
        return clients

    def _matches_client_alias_target(
        self,
        target: ControlDClientAliasTarget,
        *,
        selector_kind: str,
        selector_value: str,
    ) -> bool:
        """Return whether one client target matches one selector family."""
        if selector_kind == "mac":
            if target.client_mac_address is None:
                return False
            return self._normalize_mac_address(
                target.client_mac_address
            ) == self._normalize_mac_address(selector_value)

        if selector_kind == "ip":
            if target.client_ip_address is None:
                return False
            return self._normalize_ip_address(
                target.client_ip_address
            ) == self._normalize_ip_address(selector_value)

        candidate = {
            "name": target.endpoint_name,
            "hostname": target.client_hostname,
        }[selector_kind]
        if candidate is None:
            return False
        return self._normalize_name(candidate) == self._normalize_name(selector_value)

    @staticmethod
    def _normalize_name(value: str) -> str:
        """Normalize one human-entered selector value for exact matching."""
        return value.strip().casefold()

    @staticmethod
    def _normalize_mac_address(value: str) -> str:
        """Normalize one MAC address for exact matching."""
        return re.sub(r"[^0-9a-fA-F]", "", value).casefold()

    @staticmethod
    def _normalize_ip_address(value: str) -> str:
        """Normalize one IP address string for exact matching."""
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            return value.strip().casefold()

    def _iter_nested_clients(
        self, device_payload: dict[str, Any]
    ) -> list[tuple[str | None, dict[str, Any]]]:
        """Return nested router-client payloads when present."""
        clients = device_payload.get("clients")
        if isinstance(clients, dict):
            return [
                (key if isinstance(key, str) else None, value)
                for key, value in clients.items()
                if isinstance(value, dict)
            ]
        if isinstance(clients, list | tuple):
            return [(None, value) for value in clients if isinstance(value, dict)]
        return []

    def _client_identity(
        self, client_key: str | None, client_payload: dict[str, Any]
    ) -> str | None:
        """Build a best-effort identity for a nested client record."""
        for value in (
            client_payload.get("alias"),
            client_payload.get("name"),
            client_payload.get("host"),
            client_payload.get("mac"),
            client_key,
        ):
            if isinstance(value, str) and value:
                return self._normalize_client_identity(value)
        return None

    @staticmethod
    def _normalize_client_identity(value: str) -> str:
        """Normalize a client identity string for loose deduplication."""
        return value.strip().casefold()

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

    @staticmethod
    def _require_string(device_payload: dict[str, Any], key: str) -> str:
        """Return a required device field as a string."""
        value = device_payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Device payload is missing required string field {key!r}")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Return an optional string value."""
        return value if isinstance(value, str) and value else None
