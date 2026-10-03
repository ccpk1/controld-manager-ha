"""Tests for the get_inventory tool (Phase 2b).

The two things that matter: topology is reported from the same registry the
entities use, and the endpoint/client distinction is explicit rather than
inferred.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from custom_components.controld_manager.const import (
    DETAIL_FULL,
    DETAIL_SUMMARY,
)
from custom_components.controld_manager.managers.integration_manager import (
    IntegrationManager,
)
from custom_components.controld_manager.models import (
    ControlDAttachedProfile,
    ControlDClientAliasTarget,
    ControlDEndpointInventoryStats,
    ControlDEndpointSummary,
    ControlDProfileSummary,
    ControlDRegistry,
)

_CONFIG_ENTRY_ID = "entry-1"


def _registry() -> ControlDRegistry:
    """Return a registry with a parent, a standalone client, and a sub-client."""
    return ControlDRegistry(
        endpoint_inventory=ControlDEndpointInventoryStats(
            discovered_endpoint_count=3,
            router_client_count=2,
            protected_endpoint_count=5,
        ),
        profiles={
            "p-1": ControlDProfileSummary(profile_pk="p-1", name="Default"),
            "p-2": ControlDProfileSummary(
                profile_pk="p-2",
                name="Kids",
                paused_until=datetime(2026, 10, 4, tzinfo=UTC),
            ),
        },
        endpoints={
            "vlan60": ControlDEndpointSummary(
                device_id="vlan60",
                endpoint_pk="vlan60",
                name="Firewalla-VLAN60",
                owning_profile_pk="p-1",
                attached_profiles=(
                    ControlDAttachedProfile(profile_pk="p-1"),
                    ControlDAttachedProfile(profile_pk="p-2"),
                ),
                associated_client_count=2,
                last_active=datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
            ),
            "ipad": ControlDEndpointSummary(
                device_id="ipad",
                endpoint_pk="ipad",
                name="Chads-iPad",
                owning_profile_pk="p-2",
                attached_profiles=(ControlDAttachedProfile(profile_pk="p-2"),),
                associated_client_count=0,
                parent_device_id="vlan60",
            ),
        },
        client_alias_targets={
            "client|vlan60|aabbcc": ControlDClientAliasTarget(
                target_key="client|vlan60|aabbcc",
                source_kind="client",
                endpoint_device_id="ipad",
                endpoint_pk="ipad",
                endpoint_name="Chads-iPad",
                owning_profile_pk="p-2",
                parent_endpoint_device_id="vlan60",
                parent_endpoint_name="Firewalla-VLAN60",
                client_id="aabbcc",
                client_alias="Kadens iPad",
                client_hostname="ipad",
                client_ip_address="192.168.60.5",
                client_mac_address="aa:bb:cc:dd:ee:ff",
            ),
            "client|vlan60|ddeeff": ControlDClientAliasTarget(
                target_key="client|vlan60|ddeeff",
                source_kind="analytics_client",
                endpoint_device_id=None,
                endpoint_pk=None,
                endpoint_name=None,
                owning_profile_pk="p-1",
                parent_endpoint_device_id="vlan60",
                parent_endpoint_name="Firewalla-VLAN60",
                client_id="ddeeff",
                client_mac_address="dd:ee:ff:00:11:22",
            ),
        },
    )


class _Runtime:
    """Minimal runtime stand-in carrying one registry."""

    def __init__(self, registry: ControlDRegistry) -> None:
        """Store the registry the manager reads."""
        self.registry = registry


def _manager(registry: ControlDRegistry) -> IntegrationManager:
    """Return an integration manager attached to a runtime."""
    manager = IntegrationManager.__new__(IntegrationManager)
    manager.attach_runtime(_Runtime(registry))  # type: ignore[arg-type]
    return manager


def _build(registry: ControlDRegistry, **overrides: Any) -> dict[str, Any]:
    """Build an inventory response with sensible defaults."""
    kwargs: dict[str, Any] = {
        "config_entry_id": _CONFIG_ENTRY_ID,
        "detail": DETAIL_SUMMARY,
        "profile_ids": frozenset(),
        "endpoint_ids": frozenset(),
        "client_limit": 100,
    }
    kwargs.update(overrides)
    return _manager(registry).async_build_inventory_response(**kwargs)


def test_summary_returns_profiles_and_endpoints_without_clients() -> None:
    """The default detail omits client rows so a topology call stays small."""
    response = _build(_registry())

    assert {row["profile_name"] for row in response["profiles"]} == {"Default", "Kids"}
    assert {row["device_id"] for row in response["endpoints"]} == {"vlan60", "ipad"}
    assert "clients" not in response


def test_profile_rows_use_the_shared_endpoint_count_accessor() -> None:
    """Profile endpoint counts match the profile entities."""
    registry = _registry()
    response = _build(registry)

    rows = {row["profile_id"]: row for row in response["profiles"]}
    assert (
        rows["p-1"]["endpoint_count"]
        == registry.protected_endpoint_count_for_profile("p-1")
        == 3
    )
    assert rows["p-2"]["paused"] is True
    assert rows["p-1"]["paused"] is False


def test_endpoint_rows_expose_attachment_and_role() -> None:
    """An endpoint states its role and lists every attached profile."""
    response = _build(_registry())
    rows = {row["device_id"]: row for row in response["endpoints"]}

    vlan = rows["vlan60"]
    assert vlan["role"] == "endpoint"
    assert vlan["is_endpoint"] is True
    assert vlan["owning_profile_id"] == "p-1"
    assert vlan["owning_profile_name"] == "Default"
    assert {attached["profile_id"] for attached in vlan["attached_profiles"]} == {
        "p-1",
        "p-2",
    }
    assert vlan["associated_client_count"] == 2
    assert vlan["last_active"] == "2026-10-03T12:00:00+00:00"

    ipad = rows["ipad"]
    assert ipad["owning_profile_id"] == "p-2"
    assert ipad["parent_device_id"] == "vlan60"
    assert ipad["last_active"] is None


def test_clients_distinguish_standalone_from_sub_client() -> None:
    """A client that became its own device is flagged; one that did not is not."""
    response = _build(_registry(), detail=DETAIL_FULL)
    rows = {row["client_id"]: row for row in response["clients"]}

    standalone = rows["aabbcc"]
    assert standalone["role"] == "client"
    assert standalone["is_endpoint"] is False
    assert standalone["is_standalone_endpoint"] is True
    assert standalone["own_endpoint_id"] == "ipad"
    assert standalone["alias"] == "Kadens iPad"
    assert standalone["parent_endpoint_id"] == "vlan60"

    sub_client = rows["ddeeff"]
    assert sub_client["is_standalone_endpoint"] is False
    assert sub_client["own_endpoint_id"] is None
    assert sub_client["parent_endpoint_id"] == "vlan60"


def test_detail_full_reports_client_truncation_honestly() -> None:
    """A client cap is reported rather than silently dropping rows."""
    response = _build(_registry(), detail=DETAIL_FULL, client_limit=1)

    assert len(response["clients"]) == 1
    assert response["client_limit"] == 1
    assert response["clients_truncated"] is True


def test_filters_narrow_profiles_and_endpoints() -> None:
    """Explicit profile and endpoint selections narrow both lists."""
    by_profile = _build(_registry(), profile_ids=frozenset({"p-2"}))
    assert {row["profile_id"] for row in by_profile["profiles"]} == {"p-2"}
    # ipad owns p-2; vlan60 is only attached to p-2, so both match.
    assert {row["device_id"] for row in by_profile["endpoints"]} == {"vlan60", "ipad"}

    by_endpoint = _build(_registry(), endpoint_ids=frozenset({"ipad"}))
    assert {row["device_id"] for row in by_endpoint["endpoints"]} == {"ipad"}
    assert {row["profile_id"] for row in by_endpoint["profiles"]} == {
        "p-1",
        "p-2",
    }


def test_client_rows_respect_the_parent_endpoint_filter() -> None:
    """Scoping to one endpoint returns only that endpoint's clients."""
    response = _build(
        _registry(),
        detail=DETAIL_FULL,
        endpoint_ids=frozenset({"vlan60"}),
    )
    assert {row["client_id"] for row in response["clients"]} == {"aabbcc", "ddeeff"}


def test_inventory_is_strictly_json_serializable() -> None:
    """Both detail levels survive json.dumps, including the datetime field."""
    json.dumps(_build(_registry()))
    json.dumps(_build(_registry(), detail=DETAIL_FULL))


def test_inventory_handles_an_empty_registry() -> None:
    """An empty registry yields empty lists rather than raising."""
    response = _build(ControlDRegistry.empty(), detail=DETAIL_FULL)

    assert response["profiles"] == []
    assert response["endpoints"] == []
    assert response["clients"] == []
    assert response["clients_truncated"] is False
