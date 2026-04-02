"""Endpoint normalization and orchestration for Control D."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from ..models import (
    ControlDAttachedProfile,
    ControlDEndpointInventoryStats,
    ControlDEndpointSummary,
)
from .base_manager import BaseManager

PROFILE_KEY_PATTERN = re.compile(r"^profile\d*$")


class EndpointManager(BaseManager):
    """Own endpoint normalization and endpoint-to-profile mapping."""

    def normalize_endpoints(
        self, devices_payload: tuple[dict[str, Any], ...]
    ) -> dict[str, ControlDEndpointSummary]:
        """Normalize endpoint inventory into immutable endpoint summaries."""
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
                parent_device_id=self._extract_parent_device_id(device_payload),
            )
        return endpoints

    def summarize_inventory(
        self,
        devices_payload: tuple[dict[str, Any], ...],
        endpoints: dict[str, ControlDEndpointSummary],
    ) -> ControlDEndpointInventoryStats:
        """Return account-level endpoint totals without creating extra entities."""
        explicit_child_names_by_parent: dict[str, set[str]] = {}
        for endpoint in endpoints.values():
            if endpoint.parent_device_id is None or endpoint.name is None:
                continue
            explicit_child_names_by_parent.setdefault(
                endpoint.parent_device_id, set()
            ).add(self._normalize_client_identity(endpoint.name))

        router_client_count = 0
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
                router_client_count += 1

        discovered_endpoint_count = len(endpoints)
        return ControlDEndpointInventoryStats(
            discovered_endpoint_count=discovered_endpoint_count,
            router_client_count=router_client_count,
            protected_endpoint_count=discovered_endpoint_count + router_client_count,
        )

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
