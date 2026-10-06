"""Tests for the catalog read (Phase 2b).

`get_catalog` is the configuration read that replaced a separate policy tool, so
these tests pin the default-rule surface and the truncation contract.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from custom_components.controld_manager.const import CATALOG_TYPES
from custom_components.controld_manager.managers.integration_manager import (
    IntegrationManager,
)
from custom_components.controld_manager.models import (
    ControlDDefaultRule,
    ControlDFilter,
    ControlDProfileSummary,
    ControlDRegistry,
)

_CONFIG_ENTRY_ID = "entry-1"


class _FakeClient:
    """Minimal client stand-in that answers the redirect-location read."""

    def __init__(self, locations: list[dict[str, Any]]) -> None:
        """Store the locations this client reports."""
        self._locations = locations

    async def async_get_redirect_locations(self) -> tuple[dict[str, Any], ...]:
        """Return the stored locations."""
        return tuple(self._locations)


class _Runtime:
    """Minimal runtime stand-in carrying one registry and an optional client."""

    def __init__(
        self, registry: ControlDRegistry, *, client: Any | None = None
    ) -> None:
        """Store the registry the manager reads, and the client it fetches with."""
        self.registry = registry
        self.client = client


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
    [(1, True), (2, False), (50, False)],
    ids=["capped", "exactly-the-item-count", "complete"],
)
async def test_catalog_reports_truncation_honestly(
    limit: int, expected_truncated: bool
) -> None:
    """A capped catalog is reported, so it is never mistaken for complete.

    The catalog has two items, so a limit of two returns everything and must not
    be flagged. Only a limit below the item count drops anything.
    """
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


def test_redirect_locations_is_an_exposed_catalog_type() -> None:
    """Redirect destinations come from the catalog rather than being guessed."""
    assert "redirect_locations" in CATALOG_TYPES


async def test_redirect_location_catalog_names_each_usable_destination() -> None:
    """Each row pairs the code a redirect takes with a human-readable label.

    The code alone is unusable to a caller choosing a destination, and a name
    alone is unusable as an argument, so both are reported.
    """
    manager = IntegrationManager.__new__(IntegrationManager)
    manager.attach_runtime(  # type: ignore[arg-type]
        _Runtime(
            _registry(),
            client=_FakeClient(
                [
                    {
                        "PK": "TIA",
                        "city": "Tirana",
                        "country": "AL",
                        "country_name": "Albania",
                    },
                    {
                        "PK": "WFR",
                        "city": "Troll",
                        "country": "AQ",
                        "country_name": "Antarctica",
                    },
                    # No code means nothing to redirect to, so it is skipped.
                    {"city": "Nowhere", "country_name": "Atlantis"},
                ]
            ),
        )
    )

    response = await manager.async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="redirect_locations",
        profile_pks=_PROFILES,
        limit=50,
    )

    items: Any = response["items"]
    assert response["item_count"] == 2
    assert [row["location_code"] for row in items] == ["TIA", "WFR"]
    assert items[0]["label"] == "Tirana, Albania"
    assert items[0]["country_name"] == "Albania"
    # The text block is what a model can copy a code from.
    assert "TIA, Tirana, Albania" in response["text"]


def _filter_registry() -> ControlDRegistry:
    """Return a registry carrying two named filters on one profile."""
    return ControlDRegistry(
        profiles={"p-1": ControlDProfileSummary(profile_pk="p-1", name="Default")},
        filters_by_profile={
            "p-1": {
                "f-1": ControlDFilter(
                    filter_pk="f-1", name="Hagezi Light", enabled=True, action_do=0
                ),
                "f-2": ControlDFilter(
                    filter_pk="f-2", name="Apple", enabled=True, action_do=0
                ),
            }
        },
    )


async def test_search_finds_one_named_row_in_a_catalog_too_large_to_list() -> None:
    """`search` is what makes a named entry reachable at all.

    The service catalog runs past a thousand rows while `limit` caps at 500 and
    there is no paging, so without a filter a named entry cannot be located.
    """
    manager = _manager(_filter_registry())
    profiles = frozenset({"p-1"})

    listed = await manager.async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="filters",
        profile_pks=profiles,
        limit=50,
    )
    assert len(cast(list[Any], listed["items"])) == 2

    filtered = await manager.async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="filters",
        profile_pks=profiles,
        limit=50,
        search="apple",
    )

    matches = cast(list[Any], filtered["items"])
    assert [row["name"] for row in matches] == ["Apple"]
    # `item_count` reports the filtered total, not the pre-filter one.
    assert filtered["item_count"] == 1


async def test_search_is_case_insensitive() -> None:
    """A caller should not have to match the vendor's casing."""
    manager = _manager(_filter_registry())
    profiles = frozenset({"p-1"})

    lower = await manager.async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="filters",
        profile_pks=profiles,
        limit=50,
        search="hagezi",
    )
    upper = await manager.async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="filters",
        profile_pks=profiles,
        limit=50,
        search="HAGEZI",
    )

    assert lower["item_count"] == upper["item_count"] == 1


async def test_search_does_not_match_through_the_profile_columns() -> None:
    """Searching must not select every row via a profile it belongs to.

    Each row carries its profile's id and name. If those were searched too, a
    query for a profile name would return the whole catalog and look like a
    successful match.
    """
    manager = _manager(_filter_registry())

    response = await manager.async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="filters",
        profile_pks=frozenset({"p-1"}),
        limit=50,
        search="Default",
    )

    assert response["item_count"] == 0


async def test_search_that_matches_nothing_is_an_empty_leaf() -> None:
    """No match is an empty result carrying its count, not an error."""
    manager = _manager(_filter_registry())

    response = await manager.async_build_catalog_response(
        config_entry_id=_CONFIG_ENTRY_ID,
        catalog_type="filters",
        profile_pks=frozenset({"p-1"}),
        limit=50,
        search="zzz-no-such-entry-zzz",
    )

    assert response["items"] == []
    assert response["item_count"] == 0
