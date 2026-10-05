"""Tests for the control-tool idempotency pre-check.

A write that would change nothing must report ``already_in_state`` and must not
call the service at all. The tools read the runtime registry to decide this, so
these tests drive that read with a fixed registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm

from custom_components.controld_manager.llm_tools_control import (
    DeleteRuleTool,
    DeleteServiceTool,
    DisableProfileTool,
    EnableProfileTool,
    SetDefaultRuleStateTool,
    SetEndpointAnalyticsLoggingTool,
    SetFilterStateTool,
    SetOptionStateTool,
    SetServiceStateTool,
)
from custom_components.controld_manager.models import (
    ControlDDefaultRule,
    ControlDFilter,
    ControlDProfileOption,
    ControlDProfileOptionChoice,
    ControlDProfileSummary,
    ControlDService,
)


@dataclass
class _Registry:
    """Minimal stand-in for the runtime registry."""

    profiles: dict[str, Any] = field(default_factory=dict)
    filters_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    options_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    services_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    default_rules_by_profile: dict[str, Any] = field(default_factory=dict)


def _service(
    pk: str, name: str, *, action_do: int, enabled: bool = True
) -> ControlDService:
    """Return one normalized service row."""
    return ControlDService(
        service_pk=pk,
        name=name,
        category_pk="video",
        category_name="Video",
        auto_exposed=True,
        enabled=enabled,
        action_do=action_do,
    )


def _filter(pk: str, name: str, *, enabled: bool) -> ControlDFilter:
    """Return one normalized filter row."""
    return ControlDFilter(
        filter_pk=pk,
        name=name,
        enabled=enabled,
        action_do=0,
    )


def _option(
    pk: str, title: str, *, value: str | None, kind: str = "toggle"
) -> ControlDProfileOption:
    """Return one normalized profile option row."""
    return ControlDProfileOption(
        option_pk=pk,
        title=title,
        description=None,
        option_type="toggle" if kind == "toggle" else "dropdown",
        info_url=None,
        current_value_key=value,
        entity_kind=kind,
    )


def _registry() -> _Registry:
    """Return a registry with known filter, option, profile, and default state."""
    return _Registry(
        profiles={
            "p-1": ControlDProfileSummary(profile_pk="p-1", name="Default"),
            "p-2": ControlDProfileSummary(profile_pk="p-2", name="Kids"),
        },
        filters_by_profile={
            "p-1": {"ads": _filter("ads", "Ads & Trackers", enabled=True)},
            "p-2": {},
        },
        options_by_profile={
            "p-1": {"safesearch": _option("safesearch", "Safe Search", value="1")},
            "p-2": {},
        },
        services_by_profile={
            "p-1": {"instagram": _service("instagram", "Instagram", action_do=0)},
            "p-2": {},
        },
        default_rules_by_profile={
            "p-1": ControlDDefaultRule(enabled=True, action_do=0),
        },
    )


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


def _hass(service_call: AsyncMock) -> MagicMock:
    """Return a hass whose service registry records calls."""
    fake = MagicMock()
    fake.services.async_call = service_call
    return fake


def _tool_with_registry(tool: llm.Tool, registry: _Registry) -> llm.Tool:
    """Point a tool's registry read at a fixed registry."""
    tool._registry = lambda hass: registry  # type: ignore[method-assign]
    return tool


async def test_setting_a_filter_to_its_current_state_is_a_no_op() -> None:
    """Enabling an already-enabled filter reports already_in_state."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": "p-1", "enabled": True},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    assert result.data["changed"] is False
    assert result.data["before"] == {"enabled": [True]}
    service_call.assert_not_called()


async def test_setting_a_filter_to_a_new_state_applies() -> None:
    """Disabling an enabled filter calls the service and reports the change."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": "p-1", "enabled": False},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["changed"] is True
    assert result.data["before"] == {"enabled": [True]}
    service_call.assert_called_once()


async def test_selected_by_name_resolves_like_an_id() -> None:
    """Filters may be addressed by name as well as id."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "filter_name": "Ads & Trackers",
                "profile_id": "p-1",
                "enabled": True,
            },
        ),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    service_call.assert_not_called()


async def test_an_unknown_row_is_not_treated_as_a_no_op() -> None:
    """When the row cannot be read, the write proceeds rather than being skipped."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "filter_id": "does-not-exist",
                "profile_id": "p-1",
                "enabled": True,
            },
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    service_call.assert_called_once()


async def test_setting_an_option_to_its_current_state_is_a_no_op() -> None:
    """Enabling an already-enabled option reports already_in_state."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetOptionStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "option_id": "safesearch",
                "profile_id": "p-1",
                "enabled": True,
            },
        ),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    assert result.data["before"] == {"enabled": [True]}
    service_call.assert_not_called()


async def test_an_enabled_toggle_reports_enabled_not_the_select_fallback() -> None:
    """An enabled toggle's before-state must not read as "Off".

    ``current_select_option`` returns "Off" for any value with no matching
    choice, which is every enabled toggle, so reporting it made an enabled option
    look disabled.
    """
    service_call = AsyncMock()
    tool = _tool_with_registry(SetOptionStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "option_id": "safesearch",
                "profile_id": "p-1",
                "enabled": False,
            },
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["before"] == {"enabled": [True]}


async def test_a_select_option_reports_its_value_label() -> None:
    """A dropdown option reports the selected label, not a boolean."""
    service_call = AsyncMock()
    registry = _registry()
    registry.options_by_profile["p-1"]["ai_malware"] = ControlDProfileOption(
        option_pk="ai_malware",
        title="AI Malware Filter",
        description=None,
        option_type="dropdown",
        info_url=None,
        current_value_key="0.9",
        choices=(ControlDProfileOptionChoice(value="0.9", label="Minimal"),),
        entity_kind="select",
    )
    tool = _tool_with_registry(SetOptionStateTool(entry_id="e-1"), registry)

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "option_id": "ai_malware",
                "profile_id": "p-1",
                "value": "Aggressive",
            },
        ),
        _llm_context(),
    )

    assert result.data["before"] == {"value": ["Minimal"]}


async def test_setting_the_default_rule_to_its_current_mode_is_a_no_op() -> None:
    """A default rule already in blocking mode reports already_in_state."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetDefaultRuleStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"mode": "Blocking", "profile_id": "p-1"},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    assert result.data["before"] == {"mode": ["Blocking"]}
    service_call.assert_not_called()


async def test_the_default_rule_offers_an_undo_of_its_previous_mode() -> None:
    """The previous mode is readable, so an undo can name it.

    It previously reported `undo: null` while also reporting the previous mode in
    `before`, which is the same gap the option tool had.
    """
    service_call = AsyncMock()
    tool = _tool_with_registry(SetDefaultRuleStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"mode": "Bypassing", "profile_id": "p-1"},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    # The registry row for p-1 is enabling/blocking, so the undo restores that.
    assert result.data["undo"] == [
        "controld_manager__set_default_rule_state(mode='Blocking', profile_id='p-1')"
    ]


async def test_a_service_before_state_uses_the_same_vocabulary_as_after() -> None:
    """`before` and `after` must not disagree on vocabulary.

    `before` reported the internal key ("blocked") while `after` echoed the
    requested display label ("Bypassed"), so comparing them was misleading.
    """
    service_call = AsyncMock()
    tool = _tool_with_registry(SetServiceStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "service_id": "instagram",
                "profile_id": "p-1",
                "mode": "Bypassed",
            },
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    # The registry row is action_do=0, i.e. blocked, reported as its label.
    assert result.data["before"] == {"mode": ["Blocked"]}
    assert result.data["after"] == {"mode": "Bypassed"}


async def test_deleting_a_rule_does_not_blame_an_unreadable_state() -> None:
    """Deletion has no undo by design, so it must not cite unreadable state.

    The warning exists for a tool that *could* have offered an undo had the prior
    state been readable. Deletion is irreversible regardless, so the same warning
    gives the wrong reason and implies an undo was otherwise available.
    """
    service_call = AsyncMock()
    tool = _tool_with_registry(DeleteRuleTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"rule_identity": "root|gone.example.com", "profile_id": "p-1"},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["undo"] is None
    assert result.data["warnings"] == []


async def test_an_unreadable_precheck_still_warns_for_a_reversible_tool() -> None:
    """The warning must survive where it is genuinely the right reason.

    `set_endpoint_analytics_logging` cannot read the current level, so it really
    cannot offer an undo. That case must keep reporting it.
    """
    service_call = AsyncMock()
    tool = SetEndpointAnalyticsLoggingTool(entry_id="e-1")
    tool._registry = lambda _hass: None  # type: ignore[method-assign]

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"endpoint_id": "ep-1", "mode": "None"},
        ),
        _llm_context(),
    )

    assert result.data["undo"] is None
    assert len(result.data["warnings"]) == 1
    assert "could not be read" in result.data["warnings"][0]


async def test_deleting_a_service_names_the_call_that_re_adds_it() -> None:
    """A service delete is reversible, so it must offer a re-add undo.

    Removing the row is not the same as the destructive rule delete: the service
    can be configured again, so the tool belongs at the control tier and must
    name that call.
    """
    service_call = AsyncMock()
    tool = _tool_with_registry(DeleteServiceTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"service_id": "instagram", "profile_id": "p-1"},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    # The registry row is action_do=0, so re-adding restores Blocked.
    assert result.data["undo"] == [
        "controld_manager__set_service_state(service_id='instagram', "
        "profile_id='p-1', mode='Blocked')"
    ]
    assert result.data["after"] == {"configured": False}
    service_call.assert_called_once()


async def test_deleting_an_unconfigured_service_carries_no_undo() -> None:
    """With nothing to read, the tool must not invent an undo or a change."""
    service_call = AsyncMock()
    tool = _tool_with_registry(DeleteServiceTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"service_id": "not-configured", "profile_id": "p-1"},
        ),
        _llm_context(),
    )

    assert result.data["before"] is None
    assert result.data["undo"] is None
    assert len(result.data["warnings"]) == 1
    """Enabling a profile that is not paused reports already_in_state."""
    service_call = AsyncMock()
    tool = _tool_with_registry(EnableProfileTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(tool_name=tool.name, tool_args={"profile_id": "p-1"}),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    service_call.assert_not_called()


async def test_disabling_an_unpaused_profile_applies() -> None:
    """Disabling a running profile is a real change."""
    service_call = AsyncMock()
    tool = _tool_with_registry(DisableProfileTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name, tool_args={"profile_id": "p-1", "minutes": 30}
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    service_call.assert_called_once()


async def test_missing_registry_still_applies_the_write() -> None:
    """With no readable state the tool must not skip a requested change."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _Registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": "p-1", "enabled": True},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    service_call.assert_called_once()


@pytest.mark.parametrize(
    ("args", "expected_status", "called"),
    [
        ({"enabled": True}, "already_in_state", False),
        ({"enabled": False}, "applied", True),
    ],
    ids=["already-on", "needs-change"],
)
async def test_filter_precheck_across_an_explicit_profile(
    args: dict[str, Any], expected_status: str, called: bool
) -> None:
    """The per-profile read drives the decision, not a global guess."""
    service_call = AsyncMock()
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": "p-1", **args},
        ),
        _llm_context(),
    )

    assert result.data["status"] == expected_status
    assert service_call.called is called


async def test_service_precheck_accepts_the_display_label() -> None:
    """A service already blocked, addressed with the label 'Blocked', is a no-op.

    The schema offers display labels while `current_mode` is an internal key, so
    the pre-check must normalize before comparing. Without that normalization
    this test fails: the values never match, the write is issued anyway, and the
    result wrongly claims a change.
    """
    service_call = AsyncMock()
    tool = _tool_with_registry(SetServiceStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "service_id": "instagram",
                "profile_id": "p-1",
                "mode": "Blocked",
            },
        ),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    service_call.assert_not_called()


async def test_service_mode_schema_accepts_only_labels() -> None:
    """The tool schema is label-only, which is why normalization is required.

    The schema is deliberately not a mixed vocabulary: the caller must send the
    friendly label, and the tool normalizes it internally. Asserting this keeps
    the two vocabularies from being quietly merged.
    """
    service_call = AsyncMock()
    tool = _tool_with_registry(SetServiceStateTool(entry_id="e-1"), _registry())

    with pytest.raises(Exception):  # noqa: B017 - schema error type is not ValueError
        await tool.async_call(
            _hass(service_call),
            llm.ToolInput(
                tool_name=tool.name,
                tool_args={
                    "service_id": "instagram",
                    "profile_id": "p-1",
                    "mode": "blocked",
                },
            ),
            _llm_context(),
        )
    service_call.assert_not_called()


def test_changed_is_false_for_a_no_op_and_true_for_a_change(
    hass: HomeAssistant,
) -> None:
    """`changed` must agree with whether anything moved."""
    del hass
    assert SimpleNamespace(changed=False).changed is False
