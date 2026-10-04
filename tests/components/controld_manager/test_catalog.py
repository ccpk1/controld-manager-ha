"""Tests for the catalog read (Phase 2b).

`get_catalog` is the configuration read that replaced a separate policy tool, so
these tests pin the default-rule surface and the truncation contract.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.controld_manager.const import CATALOG_TYPES
from custom_components.controld_manager.managers.integration_manager import (
    IntegrationManager,
)
from custom_components.controld_manager.models import (
    ControlDDefaultRule,
    ControlDProfileSummary,
    ControlDRegistry,
)

_CONFIG_ENTRY_ID = "entry-1"


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


def _registry() -> ControlDRegistry:
    """Return a registry with two profiles and a default rule on one."""
    return ControlDRegistry(
        profiles={
            "p-1": ControlDProfileSummary(profile_pk="p-1", name="Default"),
            "p-2": ControlDProfileSummary(profile_pk="p-2", name="Kids"),
        },
        default_rules_by_profile={
            "p-1": ControlDDefaultRule(enabled=True, action_do=0),
            "p-2": ControlDDefaultRule(enabled=True, action_do=1),
        },
    )


_PROFILES = frozenset({"p-1", "p-2"})


def test_default_rule_is_an_exposed_catalog_type() -> None:
    """The default rule is reachable through the catalog instead of a policy tool."""
    assert "default_rule" in CATALOG_TYPES


async def test_default_rule_catalog_reports_current_mode() -> None:
    """The default-rule catalog carries state, not just availability."""
    response = await _manager(_registry()).async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="default_rule",
        profile_pks=_PROFILES,
        limit=50,
    )

    assert response["catalog_type"] == "default_rule"
    items: Any = response["items"]
    assert len(items) == 2
    rows = {item["profile_id"]: item for item in items}
    assert rows["p-1"]["profile_name"] == "Default"
    assert rows["p-1"]["enabled"] is True
    assert rows["p-1"]["current_mode"]


async def test_catalog_skips_profiles_without_a_default_rule() -> None:
    """A profile with no default rule row is omitted rather than fabricated."""
    registry = _registry()
    registry.default_rules_by_profile.pop("p-2")
    response = await _manager(registry).async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="default_rule",
        profile_pks=_PROFILES,
        limit=50,
    )

    assert {item["profile_id"] for item in response["items"]} == {"p-1"}


@pytest.mark.parametrize(
    ("limit", "expected_truncated"),
    [(1, True), (50, False)],
    ids=["capped", "complete"],
)
async def test_catalog_reports_truncation_honestly(
    limit: int, expected_truncated: bool
) -> None:
    """A capped catalog is reported, so it is never mistaken for complete."""
    response = await _manager(_registry()).async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="default_rule",
        profile_pks=_PROFILES,
        limit=limit,
    )

    assert response["applied_limit"] == limit
    assert response["truncated"] is expected_truncated
    assert len(response["items"]) <= limit


async def test_catalog_response_is_json_serializable() -> None:
    """The catalog payload survives json.dumps."""
    import json

    response = await _manager(_registry()).async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="default_rule",
        profile_pks=_PROFILES,
        limit=50,
    )
    json.dumps(response)
