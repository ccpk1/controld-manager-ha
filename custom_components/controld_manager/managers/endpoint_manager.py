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
        self.runtime.active_coordinator.schedule_write_verification()

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
        self.runtime.active_coordinator.schedule_write_verification()

    async def async_set_endpoint_profiles(
        self,
        endpoints: tuple[ControlDEndpointSummary, ...],
        *,
        profile_pk: str | None,
        profile2_pk: str | None,
        clear_profile2: bool,
    ) -> None:
        """Attach a primary and secondary profile, or clear the secondary.

        Each requested change is its own call because the verb takes one field at
        a time, and the primary cannot be cleared: an endpoint must always
        enforce one profile.
        """
        for endpoint in endpoints:
            if profile_pk is not None:
                await self.runtime.client.async_set_endpoint_profile(
                    endpoint.device_id,
                    profile_pk=profile_pk,
                    secondary=False,
                )
                endpoint = self._with_primary_profile(endpoint, profile_pk)
            if profile2_pk is not None:
                await self.runtime.client.async_set_endpoint_profile(
                    endpoint.device_id,
                    profile_pk=profile2_pk,
                    secondary=True,
                )
                endpoint = self._with_secondary_profile(endpoint, profile2_pk)
            elif clear_profile2:
                await self.runtime.client.async_clear_endpoint_secondary_profile(
                    endpoint.device_id
                )
                endpoint = self._with_secondary_profile(endpoint, None)
            # Written back after the API accepts it, like the rename and alias
            # writes. Without this the registry keeps the old value until the
            # next refresh, so a following call's `before` and `undo` would
            # report state that is no longer true.
            self.runtime.registry.endpoints[endpoint.device_id] = endpoint
        self.runtime.active_coordinator.schedule_write_verification()

    def _profile_entry(self, profile_pk: str) -> ControlDAttachedProfile:
        """Return one attached-profile entry, named from the profile registry."""
        profile = self.runtime.registry.profiles.get(profile_pk)
        return ControlDAttachedProfile(
            profile_pk=profile_pk,
            name=profile.name if profile is not None else None,
        )

    def _with_primary_profile(
        self, endpoint: ControlDEndpointSummary, profile_pk: str
    ) -> ControlDEndpointSummary:
        """Return the endpoint with a new primary, keeping any secondary.

        The primary holds the first slot, so replacing it must not disturb the
        second; this is what keeps `owning_profile_pk` and
        `secondary_profile_pk` consistent, since both are read from this list.
        """
        secondary = endpoint.attached_profiles[1:2]
        return replace(
            endpoint,
            attached_profiles=(self._profile_entry(profile_pk), *secondary),
        )

    def _with_secondary_profile(
        self, endpoint: ControlDEndpointSummary, profile_pk: str | None
    ) -> ControlDEndpointSummary:
        """Return the endpoint with its secondary set, or cleared when None.

        An endpoint always enforces one profile, so clearing the secondary keeps
        the primary rather than emptying the list.
        """
        primary = endpoint.attached_profiles[:1]
        if profile_pk is None:
            return replace(endpoint, attached_profiles=primary)
        return replace(
            endpoint,
            attached_profiles=(*primary, self._profile_entry(profile_pk)),
        )

    async def async_set_endpoint_descriptions(
        self,
        endpoints: tuple[ControlDEndpointSummary, ...],
        description: str,
    ) -> None:
        """Set one description across one or more resolved endpoints.

        An empty string clears the description, because the API drops the field
        when it is empty rather than storing a blank value.
        """
        for endpoint in endpoints:
            await self.runtime.client.async_set_endpoint_description(
                endpoint.device_id,
                description=description,
            )
            self.runtime.registry.endpoints[endpoint.device_id] = replace(
                endpoint, description=description or None
            )
        self.runtime.active_coordinator.schedule_write_verification()

    async def async_create_endpoint(
        self,
        *,
        name: str,
        profile_pk: str,
        icon: str | None,
        desc: str | None,
        stats: int | None,
    ) -> str | None:
        """Create one endpoint and return the device id the API assigned.

        The id only exists after the call, so it is returned rather than
        predicted; an undo built before the write cannot name it.
        """
        body = await self.runtime.client.async_create_endpoint(
            name=name,
            profile_pk=profile_pk,
            icon=icon,
            desc=desc,
            stats=stats,
        )
        self.runtime.active_coordinator.schedule_write_verification()
        if not isinstance(body, dict):
            return None
        device_id = body.get("device_id")
        return device_id if isinstance(device_id, str) and device_id else None

    async def async_delete_endpoints(
        self,
        endpoints: tuple[ControlDEndpointSummary, ...],
    ) -> int:
        """Delete one or more endpoints, returning how many the API removed.

        Destructive and irreversible: the endpoint, its resolver configuration,
        and the records kept against it go together, and a new endpoint is a new
        identity rather than a restored one.
        """
        deleted = 0
        for endpoint in endpoints:
            await self.runtime.client.async_delete_endpoint(endpoint.device_id)
            self.runtime.registry.endpoints.pop(endpoint.device_id, None)
            deleted += 1
        self.runtime.active_coordinator.schedule_write_verification()
        return deleted

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
        self.runtime.active_coordinator.schedule_write_verification()

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
        self.runtime.active_coordinator.schedule_write_verification()

    async def async_delete_clients(
        self,
        targets: tuple[ControlDClientAliasTarget, ...],
        *,
        delete_history: bool,
    ) -> int:
        """Delete client rows and, when asked, their stored query history.

        Deletion is destructive and there is no undo, so the API's own count of
        what it removed is returned rather than assuming every requested client
        was found. Clients are grouped by parent endpoint because the verb takes
        one parent with many client ids.
        """
        stats_endpoint = self._require_stats_endpoint()
        client_ids_by_parent: dict[str, list[str]] = {}
        for target in targets:
            client_ids_by_parent.setdefault(
                target.parent_endpoint_device_id, []
            ).append(target.client_id)

        deleted_count = 0
        for parent_device_id, client_ids in client_ids_by_parent.items():
            body = await self.runtime.client.async_delete_analytics_clients(
                stats_endpoint,
                parent_endpoint_ids=[parent_device_id],
                client_ids=client_ids,
            )
            if isinstance(body, dict):
                deleted_count += int(body.get("deletedCount") or 0)

            if delete_history:
                # Sent for the same ids that were just deleted: the history is
                # keyed by client, so it has to be named rather than inherited.
                await self.runtime.client.async_delete_analytics_client_history(
                    stats_endpoint,
                    parent_endpoint_ids=[parent_device_id],
                    client_ids=client_ids,
                )

        for target in targets:
            self.runtime.registry.client_alias_targets.pop(target.target_key, None)
        self.runtime.active_coordinator.schedule_write_verification()
        return deleted_count

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
                client_last_active=self._client_last_active(
                    endpoint_row, analytics_client_payload
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
                # No endpoint to join to: this target came only from analytics,
                # so the analytics timestamp is the only source there is.
                client_last_active=self._client_last_active(
                    None, analytics_client_payload
                ),
            )

        return targets

    def _client_last_active(
        self,
        endpoint_row: ControlDEndpointSummary | None,
        analytics_client_payload: dict[str, Any],
    ) -> datetime | None:
        """Return when this client was last active.

        A client promoted to its own standalone endpoint has its traffic
        attributed to that endpoint from then on, and Control D stops updating
        the analytics client row for it. The row's `lastActivityTime` therefore
        freezes on the day of promotion, and only the endpoint keeps moving.

        That is not hypothetical: every one of the six standalone endpoints on
        the account this was diagnosed against reported a last-active of 146 to
        174 days ago, while their endpoints reported activity minutes earlier,
        for phones that are in daily use. The endpoint is authoritative whenever
        one exists; the analytics timestamp is the only source for a client that
        has no endpoint of its own.
        """
        if endpoint_row is not None and endpoint_row.last_active is not None:
            return endpoint_row.last_active
        return self._normalize_datetime_value(
            analytics_client_payload.get("lastActivityTime")
        )

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
        client_id: str | None = None,
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
            # An id is exact, so it is tried before any human-readable selector.
            (client_id, "client_id"),
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
        endpoint_id: str | None = None,
        endpoint_name: str | None = None,
    ) -> ControlDEndpointSummary:
        """Resolve exactly one endpoint row from endpoint-scoped runtime data.

        An id is an exact, unambiguous key, so it wins over a name. A name is
        kept because it is what a person reads from the dashboard, but names are
        not guaranteed unique.
        """
        if endpoint_id is not None:
            endpoint = self.runtime.registry.endpoints.get(endpoint_id)
            if endpoint is None:
                raise ValueError("Unknown endpoint target for selector 'id'")
            return endpoint

        if endpoint_name is None:
            raise ValueError("Provide one endpoint target selector")

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
            relationship = self._extract_client_relationship(device_payload)
            endpoints[device_id] = ControlDEndpointSummary(
                device_id=device_id,
                endpoint_pk=self._optional_string(device_payload.get("PK")),
                name=self._optional_string(device_payload.get("name")),
                last_active=self._normalize_datetime_value(
                    device_payload.get("last_activity")
                    or device_payload.get("last_active")
                ),
                attached_profiles=attached_profiles,
                associated_client_count=router_client_counts_by_parent.get(
                    device_id, 0
                ),
                parent_device_id=self._extract_parent_device_id(device_payload),
                # Present only when this device is also a client under another
                # endpoint, which is how a standalone endpoint is aliased.
                parent_client_id=relationship[2] if relationship else None,
                description=self._optional_string(device_payload.get("desc")),
                icon=self._optional_string(device_payload.get("icon")),
                authorize_by_secure_dns=bool(device_payload.get("learn_ip")),
                require_authorized_ips=bool(device_payload.get("restricted")),
                legacy_dns_resolver=self._nested_string(
                    device_payload.get("legacy_ipv4"), "resolver"
                ),
                dynamic_dns_hostname=self._nested_string(
                    device_payload.get("ddns"), "hostname"
                ),
                expose_ip_host=self._nested_string(
                    device_payload.get("ddns_ext"), "host"
                ),
                prevent_deactivation_enabled=(
                    device_payload.get("deactivation_pin") is not None
                ),
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
        """Return attached profiles in upstream payload order.

        Control D sends `profile` before `profile2`, and that order is the
        definition of which is primary: the first entry becomes
        `owning_profile_pk` and the second `secondary_profile_pk`. This is the
        only place the profile list is read, so those two accessors cannot
        disagree with each other.
        """
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
        if selector_kind == "client_id":
            # The precise selector: it is what the alias API actually keys on,
            # and unlike a MAC it addresses exactly one client.
            return target.client_id == selector_value

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

    @staticmethod
    def _nested_string(value: Any, key: str) -> str | None:
        """Return one optional string from a nested payload.

        Control D omits an advanced-settings object entirely when the feature is
        off, so the object's presence with a value is what marks it enabled.
        """
        if not isinstance(value, dict):
            return None
        nested = value.get(key)
        return nested if isinstance(nested, str) and nested else None
