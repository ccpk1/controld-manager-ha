"""Tests for rule writes against a rule the profile does not expose.

`get_catalog` reports every rule upstream, but the registry only holds rules a
profile exposes. Resolution therefore falls back to a live fetch, and the write
needs those same live rows: it previously looked the rule up in the registry
alone, raising `KeyError` for an unexposed rule. Because the tool only caught
`HomeAssistantError`, that `KeyError` escaped as a bare `'group:1|example.com'`,
which reads like data rather than a failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from custom_components.controld_manager.llm_tools_control import SetRuleStateTool
from custom_components.controld_manager.managers.profile_manager import ProfileManager
from custom_components.controld_manager.models import ControlDRule

_IDENTITY = "group:1|example.com"


@dataclass
class _Registry:
    """Minimal stand-in for the runtime registry."""

    rules_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)


def _live_rule() -> ControlDRule:
    """Return one normalized rule row, as a live fetch would produce."""
    return ControlDRule(
        identity=_IDENTITY,
        rule_pk="example.com",
        order=0,
        group_pk="1",
        group_name="Localhost",
        enabled=True,
        action_do=2,
        comment="",
        ttl=None,
    )


def _manager_with_registry(hass: HomeAssistant, registry: _Registry) -> MagicMock:
    """Return a profile manager whose runtime carries the given registry."""
    manager = MagicMock(spec=ProfileManager)
    manager.runtime = MagicMock(registry=registry)
    # Bind the real lookup so the override logic under test is exercised.
    manager._rule_row = ProfileManager._rule_row.__get__(manager)
    return manager


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


def test_rule_row_prefers_live_rows_over_the_registry() -> None:
    """A live row answers for a rule the registry does not hold."""
    hass = MagicMock()
    manager = _manager_with_registry(hass, _Registry(rules_by_profile={}))
    live_rows = {"profile-1": {_IDENTITY: _live_rule()}}

    row = ProfileManager._rule_row.__get__(manager)("profile-1", _IDENTITY, live_rows)

    assert row.rule_pk == "example.com"


def test_rule_row_still_uses_the_registry_when_no_live_rows_are_given() -> None:
    """The cached path is unchanged when no live rows were fetched."""
    hass = MagicMock()
    cached = _live_rule()
    manager = _manager_with_registry(
        hass, _Registry(rules_by_profile={"profile-1": {_IDENTITY: cached}})
    )

    row = ProfileManager._rule_row.__get__(manager)("profile-1", _IDENTITY)

    assert row is cached


def test_rule_row_falls_back_to_the_registry_when_the_live_row_is_absent() -> None:
    """A live map that lacks the identity must not mask the registry row."""
    hass = MagicMock()
    cached = _live_rule()
    manager = _manager_with_registry(
        hass, _Registry(rules_by_profile={"profile-1": {_IDENTITY: cached}})
    )

    row = ProfileManager._rule_row.__get__(manager)(
        "profile-1", _IDENTITY, {"profile-1": {}}
    )

    assert row is cached


async def test_an_unexpected_error_still_returns_an_action_result() -> None:
    """A tool must never hand back a bare exception repr.

    The observed failure mode was a raw `KeyError`, whose string form is just the
    rule identity, so the model received `'group:1|example.com'` as if it were a
    result.
    """
    tool = SetRuleStateTool(entry_id="e-1")
    tool._registry = lambda _hass: None  # type: ignore[method-assign]
    fake_hass = MagicMock()
    fake_hass.services.async_call = AsyncMock(
        side_effect=KeyError(_IDENTITY),
    )

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "rule_identity": _IDENTITY,
                "profile_id": "profile-1",
                "enabled": False,
            },
        ),
        _llm_context(),
    )

    assert result.error is True
    assert result.data["status"] == "failed"
    assert result.data["changed"] is False
    assert "KeyError" in result.data["error"]
    assert _IDENTITY in result.data["error"]


async def test_a_home_assistant_error_reports_its_message() -> None:
    """The translation-keyed error path is unchanged by the broader catch."""
    tool = SetRuleStateTool(entry_id="e-1")
    tool._registry = lambda _hass: None  # type: ignore[method-assign]
    fake_hass = MagicMock()
    fake_hass.services.async_call = AsyncMock(
        side_effect=HomeAssistantError("rule rejected")
    )

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "rule_identity": _IDENTITY,
                "profile_id": "profile-1",
                "enabled": False,
            },
        ),
        _llm_context(),
    )

    assert result.data["status"] == "failed"
    assert result.data["error"] == "rule rejected"


@pytest.mark.parametrize("identity", [_IDENTITY, "example.com"])
def test_a_rule_is_matched_by_identity_or_bare_hostname(identity: str) -> None:
    """Both documented selector forms resolve to the same row."""
    from custom_components.controld_manager.services import (
        _resolve_selected_rule_identities_from_rows,
    )

    resolved = _resolve_selected_rule_identities_from_rows(
        {"profile-1": {_IDENTITY: _live_rule()}},
        frozenset({"profile-1"}),
        requested_rule_identities=[identity],
    )

    assert resolved == {"profile-1": frozenset({_IDENTITY})}
