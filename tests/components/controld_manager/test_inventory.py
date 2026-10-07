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
from custom_components.controld_manager.managers.endpoint_manager import (
    EndpointManager,
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
            endpoint_count=3,
            client_count=2,
            protected_device_count=5,
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
                attached_profiles=(ControlDAttachedProfile(profile_pk="p-2"),),
                associated_client_count=0,
                parent_device_id="vlan60",
                parent_client_id="aabbcc",
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
                client_last_active=datetime(2026, 10, 3, 9, 30, tzinfo=UTC),
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


def test_profile_rows_use_the_shared_protected_device_accessor() -> None:
    """Profile counts match the profile entities, and are named for what they count."""
    registry = _registry()
    response = _build(registry)

    rows = {row["profile_id"]: row for row in response["profiles"]}
    assert (
        rows["p-1"]["protected_device_count"]
        == registry.protected_device_count_for_profile("p-1")
        == 3
    )
    assert rows["p-2"]["paused"] is True
    assert rows["p-1"]["paused"] is False


def test_endpoint_rows_expose_attachment_and_role() -> None:
    """An endpoint states its role and names each enforced profile's slot."""
    response = _build(_registry())
    rows = {row["device_id"]: row for row in response["endpoints"]}

    vlan = rows["vlan60"]
    assert vlan["role"] == "endpoint"
    assert vlan["is_endpoint"] is True
    # One list, with the slot named, rather than a primary/secondary pair plus
    # a copy of the list that could disagree with it.
    assert vlan["enforced_profiles"] == [
        {"profile_id": "p-1", "profile_name": "Default", "slot": "primary"},
        {"profile_id": "p-2", "profile_name": "Kids", "slot": "secondary"},
    ]
    assert "owning_profile_id" not in vlan
    assert "attached_profiles" not in vlan
    assert vlan["associated_client_count"] == 2
    assert vlan["last_active"] == "2026-10-03T12:00:00+00:00"

    ipad = rows["ipad"]
    assert [entry["slot"] for entry in ipad["enforced_profiles"]] == ["primary"]
    assert ipad["enforced_profiles"][0]["profile_id"] == "p-2"
    assert ipad["parent_device_id"] == "vlan60"
    assert ipad["last_active"] is None


def test_standalone_endpoint_row_exposes_the_client_identity_it_came_from() -> None:
    """A client promoted to its own endpoint is aliased by its client id, so the
    endpoint row carries it: an endpoint itself has no MAC to fall back on.
    """
    response = _build(_registry())
    rows = {row["device_id"]: row for row in response["endpoints"]}

    assert rows["ipad"]["parent_client_id"] == "aabbcc"
    assert rows["vlan60"]["parent_client_id"] is None


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
    assert sub_client["last_active"] is None


def test_client_rows_report_recency_so_stale_rows_can_be_told_apart() -> None:
    """Control D keeps rows for decommissioned addresses, so recency is the
    signal that separates a live device from leftover history.
    """
    response = _build(_registry(), detail=DETAIL_FULL)
    rows = {row["client_id"]: row for row in response["clients"]}

    assert rows["aabbcc"]["last_active"] == "2026-10-03T09:30:00+00:00"


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


def _endpoint_rows(payload: dict[str, Any]) -> dict[str, Any]:
    """Return normalized endpoint rows for one synthetic device payload."""
    return EndpointManager().normalize_endpoints((payload,))


def test_advanced_settings_map_to_the_dashboard_labels() -> None:
    """Each Advanced Settings row reads from its own API field.

    Control D omits the field entirely when the feature is off, so the tests
    cover both the present and absent shapes: absence is what "off" looks like,
    not a null.
    """
    rows = _endpoint_rows(
        {
            "device_id": "ep-1",
            "PK": "ep-1",
            "name": "Endpoint-Test",
            "desc": "kitchen tablet",
            "icon": "desktop-linux",
            "learn_ip": 1,
            "restricted": 1,
            "legacy_ipv4": {"resolver": "76.76.2.11", "status": 1},
            "ddns": {
                "status": 1,
                "subdomain": "my-sub",
                "hostname": "my-sub.controld.xyz",
                "record": "2607:f0c8::1",
            },
            "ddns_ext": {"status": 1, "host": "home.example.com"},
            "deactivation_pin": 1234,
        }
    )
    endpoint = rows["ep-1"]

    assert endpoint.description == "kitchen tablet"
    assert endpoint.icon == "desktop-linux"
    # Authorize by Secure DNS.
    assert endpoint.authorize_by_secure_dns is True
    # Require Authorized IPs.
    assert endpoint.require_authorized_ips is True
    # Legacy DNS, publishing plain resolver IPs.
    assert endpoint.legacy_dns_enabled is True
    assert endpoint.legacy_dns_resolver == "76.76.2.11"
    # Authorize by Dynamic DNS.
    assert endpoint.dynamic_dns_enabled is True
    assert endpoint.dynamic_dns_hostname == "my-sub.controld.xyz"
    # Expose IP via DNS.
    assert endpoint.expose_ip_enabled is True
    assert endpoint.expose_ip_host == "home.example.com"
    # Prevent Deactivation: presence of a PIN is all that is reported.
    assert endpoint.prevent_deactivation_enabled is True


def test_the_analytics_logging_level_is_read_from_the_stats_field() -> None:
    """`stats` is the logging level, and it is read rather than only written.

    `GET /devices` returns it on every row, so without this the level could be
    set but never read back, leaving a write unable to name what it replaced.
    An unrecognised value is not guessed at.
    """
    manager = EndpointManager()
    for stats, expected in ((2, "full"), (1, "some"), (0, "none"), (9, None)):
        rows = manager.normalize_endpoints(
            ({"device_id": "ep-1", "PK": "ep-1", "name": "A", "stats": stats},)
        )
        assert rows["ep-1"].analytics_logging == expected, stats

    # Absent entirely, which is how the API reports a field it does not send.
    rows = manager.normalize_endpoints(
        ({"device_id": "ep-1", "PK": "ep-1", "name": "A"},)
    )
    assert rows["ep-1"].analytics_logging is None


def test_advanced_settings_default_off_when_the_api_omits_them() -> None:
    """An omitted field means the feature is off, and must not read as enabled."""
    endpoint = _endpoint_rows(
        {"device_id": "ep-2", "PK": "ep-2", "name": "Bare", "learn_ip": 0}
    )["ep-2"]

    assert endpoint.authorize_by_secure_dns is False
    assert endpoint.require_authorized_ips is False
    assert endpoint.legacy_dns_enabled is False
    assert endpoint.dynamic_dns_enabled is False
    assert endpoint.expose_ip_enabled is False
    assert endpoint.legacy_dns_resolver is None
    assert endpoint.dynamic_dns_hostname is None
    assert endpoint.expose_ip_host is None
    assert endpoint.prevent_deactivation_enabled is False


def test_secondary_profile_is_captured_from_the_enforced_list() -> None:
    """An endpoint may enforce two profiles, and the second must be visible.

    Without it a caller cannot tell what a profile change would overwrite, and a
    reverse of that change would clear the secondary instead of restoring it.
    Both are read from the one list, so the row and the accessors cannot disagree.
    """
    endpoint = _endpoint_rows(
        {
            "device_id": "ep-1",
            "PK": "ep-1",
            "name": "chads-phone",
            "profile": {"PK": "primary-pk", "name": "Chads Phone"},
            "profile2": {"PK": "secondary-pk", "name": "Default"},
        }
    )["ep-1"]

    assert endpoint.owning_profile_pk == "primary-pk"
    assert endpoint.secondary_profile_pk == "secondary-pk"
    assert [entry.profile_pk for entry in endpoint.attached_profiles] == [
        "primary-pk",
        "secondary-pk",
    ]
    # The names come along, so a row needs no second lookup to show one.
    assert [entry.name for entry in endpoint.attached_profiles] == [
        "Chads Phone",
        "Default",
    ]


def test_secondary_profile_is_absent_when_only_one_is_enforced() -> None:
    """A single-profile endpoint reports no secondary rather than a blank one."""
    endpoint = _endpoint_rows(
        {
            "device_id": "ep-2",
            "PK": "ep-2",
            "name": "Bare",
            "profile": {"PK": "primary-pk", "name": "Default"},
        }
    )["ep-2"]

    assert endpoint.owning_profile_pk == "primary-pk"
    assert endpoint.secondary_profile_pk is None
