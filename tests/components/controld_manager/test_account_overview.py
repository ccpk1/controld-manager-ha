"""Tests for the account overview tool (Phase 2a).

The central guarantee is that the overview can never disagree with the account
and profile entities. Both read the same ``ControlDRegistry`` accessors, so these
tests pin that wiring rather than re-deriving the numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.controld_manager.managers.integration_manager import (
    IntegrationManager,
)
from custom_components.controld_manager.models import (
    ControlDAccountAnalytics,
    ControlDAttachedProfile,
    ControlDEndpointInventoryStats,
    ControlDEndpointSummary,
    ControlDProfileSummary,
    ControlDRegistry,
    ControlDUser,
)

_CONFIG_ENTRY_ID = "entry-1"


def _registry() -> ControlDRegistry:
    """Return a registry with known counts and analytics."""
    return ControlDRegistry(
        user=ControlDUser(
            instance_id="user-1",
            account_pk="pk-1",
            stats_endpoint="america",
            # GET /users documents both of these as integers. A string here
            # would hide the type bug that made them parse as null live.
            status=1,
            last_active=1669595046,
        ),
        account_analytics=ControlDAccountAnalytics(
            total_queries=1000,
            blocked_queries=600,
            bypassed_queries=380,
            redirected_queries=20,
            blocked_queries_ratio=60.0,
            start_time=datetime(2026, 10, 2, 20, 0, tzinfo=UTC),
            end_time=datetime(2026, 10, 3, 21, 0, tzinfo=UTC),
        ),
        profile_analytics_by_profile={
            "p-1": ControlDAccountAnalytics(
                total_queries=700,
                blocked_queries=500,
                bypassed_queries=190,
                redirected_queries=10,
            )
        },
        endpoint_inventory=ControlDEndpointInventoryStats(
            discovered_endpoint_count=9,
            router_client_count=4,
            protected_endpoint_count=13,
        ),
        profiles={
            "p-1": ControlDProfileSummary(profile_pk="p-1", name="Default"),
            "p-2": ControlDProfileSummary(
                profile_pk="p-2",
                name="Kids",
                paused_until=datetime(2026, 10, 3, 23, 0, tzinfo=UTC),
            ),
        },
        endpoints={
            "ep-1": ControlDEndpointSummary(
                device_id="ep-1",
                endpoint_pk="ep-1",
                name="VLAN60",
                owning_profile_pk="p-1",
                attached_profiles=(ControlDAttachedProfile(profile_pk="p-1"),),
                associated_client_count=3,
            )
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


def test_registry_count_accessors_are_the_single_source() -> None:
    """The shared accessors expose the entity counts, not raw dict lengths."""
    registry = _registry()

    # The endpoint count is the protected count, not len(registry.endpoints).
    assert registry.endpoint_count == 13
    assert registry.endpoint_count != len(registry.endpoints)
    assert registry.discovered_endpoint_count == 9
    assert registry.router_client_count == 4
    assert registry.profile_count == 2
    assert registry.protected_endpoint_count_for_profile("p-1") == 4


def test_overview_account_counts_match_the_registry_accessors() -> None:
    """Overview account counts are exactly what the account entities report."""
    registry = _registry()
    overview = _manager(registry).async_build_account_overview_response(
        config_entry_id=_CONFIG_ENTRY_ID
    )

    account: Any = overview["account"]
    assert account["profile_count"] == registry.profile_count == 2
    assert account["endpoint_count"] == registry.endpoint_count == 13
    assert (
        account["discovered_endpoint_count"] == registry.discovered_endpoint_count == 9
    )
    assert account["router_client_count"] == registry.router_client_count == 4
    assert account["region"] == "america"
    # Integer, not a stringified integer: GET /users documents it as an integer
    # and the field was silently null in production until the parse was fixed.
    assert account["status"] == registry.user.status == 1
    assert isinstance(account["status"], int)


def test_overview_profile_rows_match_the_entity_accessors() -> None:
    """Per-profile rows use the same counts and analytics as the profile entities."""
    registry = _registry()
    overview = _manager(registry).async_build_account_overview_response(
        config_entry_id=_CONFIG_ENTRY_ID
    )

    rows = {row["profile_id"]: row for row in overview["profiles"]}
    assert set(rows) == {"p-1", "p-2"}

    default_row = rows["p-1"]
    assert default_row["profile_name"] == "Default"
    assert (
        default_row["endpoint_count"]
        == registry.protected_endpoint_count_for_profile("p-1")
        == 4
    )
    assert default_row["blocked_queries"] == 500
    assert default_row["bypassed_queries"] == 190
    assert default_row["redirected_queries"] == 10
    assert default_row["paused"] is False

    kids_row = rows["p-2"]
    assert kids_row["endpoint_count"] == 0
    assert kids_row["paused"] is True
    assert kids_row["blocked_queries"] is None


def test_overview_is_strictly_json_serializable() -> None:
    """Both the account block and the profile rows survive json.dumps."""
    import json

    overview = _manager(_registry()).async_build_account_overview_response(
        config_entry_id=_CONFIG_ENTRY_ID
    )
    json.dumps(overview)


def test_overview_handles_an_empty_registry() -> None:
    """An empty registry yields zeroed counts rather than raising."""
    overview = _manager(ControlDRegistry.empty()).async_build_account_overview_response(
        config_entry_id=_CONFIG_ENTRY_ID
    )

    assert overview["account"]["profile_count"] == 0
    assert overview["account"]["endpoint_count"] == 0
    assert overview["account"]["region"] is None
    assert overview["account"]["analytics"] == {}
    assert overview["profiles"] == []


@pytest.mark.parametrize("analytics_present", [True, False], ids=["with", "without"])
def test_overview_analytics_block_reflects_availability(
    analytics_present: bool,
) -> None:
    """A missing analytics snapshot serializes to an empty block, not a fake zero."""
    registry = _registry()
    if not analytics_present:
        registry = ControlDRegistry(
            user=registry.user,
            endpoint_inventory=registry.endpoint_inventory,
            profiles=registry.profiles,
            endpoints=registry.endpoints,
        )

    overview = _manager(registry).async_build_account_overview_response(
        config_entry_id=_CONFIG_ENTRY_ID
    )
    analytics = overview["account"]["analytics"]
    assert bool(analytics) is analytics_present
