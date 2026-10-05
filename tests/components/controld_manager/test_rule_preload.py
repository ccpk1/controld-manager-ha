"""Tests for the rule tool's live preload.

The registry only holds rules a profile exposes. For a rule it does not expose,
the pre-check, the no-op check, and the undo were all blind: `before` was null,
`already_in_state` never triggered, and `undo` was always null — which defeated
the redirect-restoring undo added for D44, in exactly the case that motivated it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import Context
from homeassistant.helpers import llm

from custom_components.controld_manager.llm_tools_control import SetRuleStateTool
from custom_components.controld_manager.models import ControlDRule

_IDENTITY = "group:1|example.com"


def _rule(action_do: int = 2, via: str | None = "127.0.0.1") -> ControlDRule:
    """Return one normalized redirect rule row."""
    return ControlDRule(
        identity=_IDENTITY,
        rule_pk="example.com",
        order=0,
        group_pk="1",
        group_name="Localhost",
        enabled=True,
        action_do=action_do,
        comment="",
        ttl=None,
        via=via,
    )


def _tool(*, registry_rules: dict[str, Any] | None, entry: Any = None) -> llm.Tool:
    """Return a rule tool backed by a registry and an optional config entry."""
    tool = SetRuleStateTool(entry_id="e-1")
    registry = MagicMock()
    registry.rules_by_profile = {"profile-1": registry_rules or {}}
    registry.profiles = {"profile-1": MagicMock()}
    tool._registry = lambda _hass: registry  # type: ignore[method-assign]

    fake_hass = MagicMock()
    fake_hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    tool._hass = fake_hass
    return tool


def _hass_for(tool: llm.Tool) -> Any:
    """Return the hass the tool was built with."""
    return tool._hass


def _manager(rules: dict[str, ControlDRule]) -> Any:
    """Return an integration manager that loads the given rules."""
    manager = MagicMock()
    manager.async_load_live_rules = AsyncMock(return_value={"profile-1": ({}, rules)})
    return manager


def _entry(manager: Any) -> Any:
    """Return a config entry exposing the given integration manager."""
    return MagicMock(
        runtime_data=MagicMock(
            managers=MagicMock(integration=manager),
        )
    )


async def test_the_registry_is_used_without_fetching_when_it_can_answer() -> None:
    """An exposed rule must not cost an extra request."""
    tool = _tool(registry_rules={_IDENTITY: _rule()})
    manager = _manager({})

    await tool._async_preload(_hass_for(tool), {"rule_identity": _IDENTITY})

    manager.async_load_live_rules.assert_not_awaited()
    assert tool._preloaded_rules is None


async def test_an_unexposed_rule_is_fetched() -> None:
    """The registry cannot answer, so the rule is loaded from the API."""
    rule = _rule()
    manager = _manager({_IDENTITY: rule})
    tool = _tool(registry_rules={}, entry=_entry(manager))

    await tool._async_preload(_hass_for(tool), {"rule_identity": _IDENTITY})

    manager.async_load_live_rules.assert_awaited_once()
    assert tool._preloaded_rules == {"profile-1": {_IDENTITY: rule}}


async def test_the_preloaded_row_backs_the_precheck_and_undo() -> None:
    """With preloaded rows the tool reports real state and a usable undo."""
    rule = _rule()
    tool = _tool(registry_rules={})
    tool._preloaded_rules = {"profile-1": {_IDENTITY: rule}}

    before: Any = tool._before(_hass_for(tool), {"rule_identity": _IDENTITY})
    undo = tool._undo(_hass_for(tool), {"rule_identity": _IDENTITY})

    assert before["action"] == ["redirect"]
    assert before["redirect_target"] == ["127.0.0.1"]
    assert undo is not None
    assert "redirect_target='127.0.0.1'" in undo[0]


async def test_the_precheck_reports_no_op_from_a_preloaded_row() -> None:
    """`already_in_state` works for an unexposed rule once it is preloaded."""
    tool = _tool(registry_rules={})
    tool._preloaded_rules = {"profile-1": {_IDENTITY: _rule()}}

    assert (
        tool._is_already_in_state(
            _hass_for(tool), {"rule_identity": _IDENTITY, "enabled": True}
        )
        is True
    )
    assert (
        tool._is_already_in_state(
            _hass_for(tool), {"rule_identity": _IDENTITY, "enabled": False}
        )
        is False
    )


async def test_without_a_preload_the_tool_is_blind_as_before() -> None:
    """The old behaviour is preserved when nothing can be loaded.

    This is the case the tests above exist to fix, so it is pinned to prove the
    fix is what changes the outcome rather than something incidental.
    """
    tool = _tool(registry_rules={})

    before = tool._before(_hass_for(tool), {"rule_identity": _IDENTITY})
    undo = tool._undo(_hass_for(tool), {"rule_identity": _IDENTITY})

    assert before is None
    assert undo is None


async def test_the_preloaded_state_is_dropped_after_the_call() -> None:
    """Preloaded rows are per-call and must not leak into the next call."""
    rule = _rule()
    manager = _manager({_IDENTITY: rule})
    tool = _tool(registry_rules={}, entry=_entry(manager))

    await tool._async_preload(_hass_for(tool), {"rule_identity": _IDENTITY})
    assert tool._preloaded_rules is not None

    tool._clear_preload()

    assert tool._preloaded_rules is None


@pytest.mark.parametrize(
    "identity",
    ["some-other.example.com", "root|unrelated.example.com"],
    ids=["unknown-hostname", "unknown-identity"],
)
async def test_a_selector_the_registry_lacks_triggers_one_fetch(
    identity: str,
) -> None:
    """An identity the registry does not hold is fetched, exactly once.

    `rule_identity` is required by the schema, so a call always carries one; the
    interesting case is a well-formed selector that simply is not exposed.
    """
    manager = _manager({_IDENTITY: _rule()})
    tool = _tool(registry_rules={}, entry=_entry(manager))

    await tool._async_preload(_hass_for(tool), {"rule_identity": identity})

    manager.async_load_live_rules.assert_awaited_once()
    # The fetched rows are stored whole, so the identity need not match to be
    # available; matching happens in `_matching_rules`.
    assert tool._preloaded_rules is not None


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def test_a_full_call_preloads_then_clears() -> None:
    """The whole call path preloads, reports the real state, and cleans up."""
    rule = _rule()
    manager = _manager({_IDENTITY: rule})
    tool = _tool(registry_rules={}, entry=_entry(manager))
    fake_hass = _hass_for(tool)
    service_call = AsyncMock()
    fake_hass.services.async_call = service_call

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"rule_identity": _IDENTITY, "enabled": False},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["before"] is not None
    assert result.data["undo"] is not None
    assert result.data["warnings"] == []
    service_call.assert_awaited_once()
    assert tool._preloaded_rules is None
