"""Tests for how a rule write picks its contract.

Control D preserves the rest of a rule for a status-only update, but rejects a
restated redirect action that carries no target ("400 40003 Invalid rule action
was provided"). The write path therefore has to choose between three contracts,
and choosing wrongly broke toggling a redirect rule.

These drive the dispatch directly, so each branch is covered without needing a
redirect rule in the profile fixtures.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.controld_manager.managers.profile_manager import ProfileManager
from custom_components.controld_manager.models import ControlDRule

_BLOCK = 0
_BYPASS = 1
_REDIRECT = 2


def _rule(action_do: int) -> ControlDRule:
    """Return one normalized rule row with the given action."""
    return ControlDRule(
        identity="group:1|example.com",
        rule_pk="example.com",
        order=0,
        group_pk="1",
        group_name="Localhost",
        enabled=True,
        action_do=action_do,
        comment="",
        ttl=None,
    )


def _manager() -> MagicMock:
    """Return a manager whose client records every rule write."""
    manager = MagicMock(spec=ProfileManager)
    client = MagicMock()
    client.async_set_profile_rule = AsyncMock()
    client.async_set_profile_rule_enabled = AsyncMock()
    client.async_update_profile_rule_rich = AsyncMock()
    manager.runtime = MagicMock()
    manager.runtime.client = client
    # Bind the real dispatch so the branch logic under test runs.
    manager._async_write_rule = ProfileManager._async_write_rule.__get__(manager)
    return manager


@pytest.mark.parametrize(
    "action_do",
    [_BLOCK, _BYPASS, _REDIRECT],
    ids=["block", "bypass", "redirect"],
)
async def test_an_unchanged_action_uses_a_status_only_write(action_do: int) -> None:
    """A toggle sends no action, so Control D keeps the rule as it is.

    This is what makes a redirect rule toggleable: `do: 2` on its own is rejected
    because a redirect action carries a target the action value does not.
    """
    manager = _manager()
    rule = _rule(action_do)

    await ProfileManager._async_write_rule.__get__(manager)(
        profile_pk="profile-1",
        rule_row=rule,
        next_enabled=False,
        next_action_do=action_do,
        next_comment="",
        payload_ttl=None,
        uses_rich_update=False,
        via=None,
        via_v6=None,
    )

    client = manager.runtime.client
    client.async_set_profile_rule_enabled.assert_awaited_once_with(
        "profile-1", "example.com", enabled=False
    )
    client.async_set_profile_rule.assert_not_awaited()
    client.async_update_profile_rule_rich.assert_not_awaited()


async def test_a_changed_action_still_sends_the_action() -> None:
    """When the action really changes it must be sent, or the write does nothing.

    Stripping the action whenever the target is a redirect would silently drop a
    genuine mode change, which is the regression this guards against.
    """
    manager = _manager()
    rule = _rule(_REDIRECT)

    await ProfileManager._async_write_rule.__get__(manager)(
        profile_pk="profile-1",
        rule_row=rule,
        next_enabled=True,
        next_action_do=_BLOCK,
        next_comment="",
        payload_ttl=None,
        uses_rich_update=False,
        via=None,
        via_v6=None,
    )

    client = manager.runtime.client
    client.async_set_profile_rule.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=_BLOCK,
        group_pk="1",
        ttl=None,
        comment="",
    )
    client.async_set_profile_rule_enabled.assert_not_awaited()


async def test_a_rich_change_uses_the_rich_contract() -> None:
    """A comment, TTL, or redirect change needs the rich hostname-based write."""
    manager = _manager()
    rule = _rule(_REDIRECT)

    await ProfileManager._async_write_rule.__get__(manager)(
        profile_pk="profile-1",
        rule_row=rule,
        next_enabled=True,
        next_action_do=_REDIRECT,
        next_comment="note",
        payload_ttl=123,
        uses_rich_update=True,
        via="CLE",
        via_v6=None,
    )

    client = manager.runtime.client
    client.async_update_profile_rule_rich.assert_awaited_once_with(
        "profile-1",
        "example.com",
        enabled=True,
        action_do=_REDIRECT,
        group_pk="1",
        comment="note",
        ttl=123,
        via="CLE",
        via_v6=None,
    )
    client.async_set_profile_rule_enabled.assert_not_awaited()
    client.async_set_profile_rule.assert_not_awaited()


async def test_a_rich_change_wins_over_an_unchanged_action() -> None:
    """An unchanged action with a rich change must not take the status-only path.

    Otherwise the comment or TTL would be silently dropped.
    """
    manager = _manager()
    rule = _rule(_REDIRECT)

    await ProfileManager._async_write_rule.__get__(manager)(
        profile_pk="profile-1",
        rule_row=rule,
        next_enabled=True,
        next_action_do=_REDIRECT,
        next_comment="note",
        payload_ttl=None,
        uses_rich_update=True,
        via=None,
        via_v6=None,
    )

    client = manager.runtime.client
    client.async_update_profile_rule_rich.assert_awaited_once()
    client.async_set_profile_rule_enabled.assert_not_awaited()
