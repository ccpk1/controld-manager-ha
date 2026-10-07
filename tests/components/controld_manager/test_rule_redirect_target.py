"""Tests for reading and reverting a redirect rule's destination.

A redirect rule's action alone does not describe it: `do: 2` with no target is
meaningless, and Control D rejects a redirect write that carries no target. The
destination was previously discarded during normalization, so nothing could
report where a redirected domain was sent and no undo could restore it.

The normalization test matters most: the destination is only useful if it
survives the trip from the API payload into the model.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers import llm

from custom_components.controld_manager.llm_tools_control import SetRuleStateTool
from custom_components.controld_manager.managers.integration_manager import (
    IntegrationManager,
)
from custom_components.controld_manager.models import ControlDRule

_IDENTITY = "group:1|example.com"


def _rule(
    *,
    action_do: int,
    enabled: bool = True,
    via: str | None = None,
    via_v6: str | None = None,
    ttl: int | None = None,
) -> ControlDRule:
    """Return one normalized rule row."""
    return ControlDRule(
        identity=_IDENTITY,
        rule_pk="example.com",
        order=0,
        group_pk="1",
        group_name="Localhost",
        enabled=enabled,
        action_do=action_do,
        comment="",
        ttl=ttl,
        via=via,
        via_v6=via_v6,
    )


def _payload(action: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return the raw rules payload shape the client hands to normalization."""
    return ({"PK": "example.com", "order": 1, "group": 1, "action": action},)


@pytest.mark.parametrize(
    ("action", "expected_target", "expected_type"),
    [
        pytest.param(
            {"do": 2, "status": 1, "via": "127.0.0.1"},
            "127.0.0.1",
            "ipv4",
            id="ipv4-proxy",
        ),
        pytest.param(
            {"do": 3, "status": 1, "via": "CLE"}, "CLE", "location", id="location"
        ),
        pytest.param(
            {"do": 3, "status": 1, "via": "LOCAL"}, "LOCAL", "location", id="local"
        ),
        pytest.param({"do": 3, "status": 1, "via": "?"}, "?", "location", id="random"),
        pytest.param(
            {"do": 2, "status": 1, "via": "-1", "via_v6": "a:b:c:d:e:f::"},
            "a:b:c:d:e:f::",
            "ipv6",
            id="ipv6-proxy",
        ),
        pytest.param({"do": 0, "status": 1}, None, None, id="block"),
        pytest.param({"do": 1, "status": 1}, None, None, id="bypass"),
        pytest.param(
            {"do": 2, "status": 1, "via": "-1"}, None, None, id="sentinel-only"
        ),
    ],
)
def test_normalization_captures_the_redirect_destination(
    action: dict[str, Any], expected_target: str | None, expected_type: str | None
) -> None:
    """The destination survives from the API payload into the model.

    This is the link that was missing: `action.via` was never read, so every
    destination was discarded regardless of what the API returned.
    """
    rules = IntegrationManager._normalize_rules((), _payload(action))
    rule = rules[_IDENTITY]

    assert rule.redirect_target == expected_target
    assert rule.redirect_write_type == expected_type


@pytest.mark.parametrize(
    ("action", "expected_target", "expected_type"),
    [
        pytest.param(
            {"do": 2, "status": 1, "via": "127.0.0.1"},
            "127.0.0.1",
            "ipv4",
            id="ipv4-proxy",
        ),
        pytest.param(
            {"do": 3, "status": 1, "via": "CLE"}, "CLE", "location", id="location"
        ),
        pytest.param({"do": 0, "status": 1}, None, None, id="block-folder"),
        pytest.param({"do": 1, "status": 1}, None, None, id="allow-folder"),
    ],
)
def test_normalization_captures_a_folders_redirect_destination(
    action: dict[str, Any], expected_target: str | None, expected_type: str | None
) -> None:
    """A folder applies one action to every rule in it, destination included.

    The folder payload carries `action.via` exactly as a rule does, so it was
    being discarded the same way.
    """
    groups = IntegrationManager._normalize_rule_groups(
        ({"PK": 1, "group": "Localhost", "action": action, "count": 1},)
    )
    group = groups["1"]

    assert group.redirect_target == expected_target
    assert group.redirect_write_type == expected_type


def test_the_redirect_destination_is_none_for_a_non_redirect_action() -> None:
    """A block rule must not report a destination even if one is present."""
    rules = IntegrationManager._normalize_rules(
        (), _payload({"do": 0, "status": 1, "via": "CLE"})
    )

    assert rules[_IDENTITY].redirect_target is None


def _tool_with_rule(rule: ControlDRule) -> llm.Tool:
    """Point a rule tool's registry read at one rule."""
    tool = SetRuleStateTool(entry_id="e-1")
    registry = MagicMock()
    registry.rules_by_profile = {"profile-1": {_IDENTITY: rule}}
    registry.profiles = {"profile-1": MagicMock()}
    tool._registry = lambda _hass: registry  # type: ignore[method-assign]
    return tool


@pytest.mark.parametrize(
    ("via", "action_do", "expected_type"),
    [
        pytest.param("CLE", 3, "location", id="location"),
        pytest.param("127.0.0.1", 2, "ipv4", id="ipv4"),
        pytest.param("LOCAL", 3, "location", id="local-sentinel"),
    ],
)
def test_the_undo_restates_a_redirect_with_its_destination(
    via: str, action_do: int, expected_type: str
) -> None:
    """Reverting a redirect must include the target, or Control D rejects it."""
    tool = _tool_with_rule(_rule(action_do=action_do, via=via))

    undo = tool._undo(MagicMock(), {"rule_identity": _IDENTITY})

    assert undo is not None
    call = undo[0]
    assert "mode='redirect'" in call
    assert f"redirect_target={via!r}" in call
    assert f"redirect_target_type={expected_type!r}" in call


def test_the_undo_of_a_block_rule_does_not_restate_a_target() -> None:
    """A non-redirect rule has no destination to restore."""
    tool = _tool_with_rule(_rule(action_do=0))

    undo = tool._undo(MagicMock(), {"rule_identity": _IDENTITY})

    assert undo is not None
    assert "redirect_target" not in undo[0]
    assert "mode='block'" in undo[0]


def test_the_undo_restores_disabled_state_and_expiry() -> None:
    """The previous enabled state and expiry are part of the reverse call."""
    tool = _tool_with_rule(_rule(action_do=0, enabled=False, ttl=1234))

    undo = tool._undo(MagicMock(), {"rule_identity": _IDENTITY})

    assert undo is not None
    assert "enabled=False" in undo[0]
    assert "expire_at=1234" in undo[0]


def test_the_before_state_includes_the_redirect_destination() -> None:
    """An agent needs the destination to describe a redirected rule."""
    tool = _tool_with_rule(_rule(action_do=3, via="CLE"))

    before: Any = tool._before(MagicMock(), {"rule_identity": _IDENTITY})

    assert before["targets"] == [
        {
            "rule_identity": _IDENTITY,
            "enabled": True,
            "mode": "redirect",
            "redirect_target": "CLE",
        }
    ]


def test_the_before_state_omits_the_key_when_nothing_redirects() -> None:
    """A block rule must not carry a misleading null destination."""
    tool = _tool_with_rule(_rule(action_do=0))

    before: Any = tool._before(MagicMock(), {"rule_identity": _IDENTITY})

    assert "redirect_target" not in before


def test_a_redirect_is_already_in_state_only_for_the_same_destination() -> None:
    """Changing only the destination must not be mistaken for a no-op."""
    service_call = AsyncMock()
    tool = _tool_with_rule(_rule(action_do=3, via="CLE"))
    fake_hass = MagicMock()
    fake_hass.services.async_call = service_call

    same = tool._is_already_in_state(
        fake_hass,
        {"rule_identity": _IDENTITY, "redirect_target": "CLE"},
    )
    different = tool._is_already_in_state(
        fake_hass,
        {"rule_identity": _IDENTITY, "redirect_target": "WFR"},
    )

    assert same is True
    assert different is False


def test_the_after_state_echoes_a_requested_destination() -> None:
    """A destination change is reported back to the caller."""
    tool = _tool_with_rule(_rule(action_do=3, via="CLE"))

    after = tool._after({"redirect_target": "WFR", "redirect_target_type": "location"})

    assert after == {"redirect_target": "WFR", "redirect_target_type": "location"}
