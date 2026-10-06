"""Tests for the control-tool undo calls.

An undo has to restore the *previous* state, which only the runtime registry
knows, so the tool reads it before the write. These tests drive that read with a
fixed registry and assert the emitted call, because an undo that names the wrong
value is worse than no undo at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm

from custom_components.controld_manager.llm_tools_control import (
    ClearClientAliasTool,
    RenameEndpointTool,
    SetClientAliasTool,
    SetFilterStateTool,
    SetOptionStateTool,
    SetServiceStateTool,
)


@dataclass
class _Endpoint:
    """Minimal stand-in for a normalized endpoint row."""

    name: str


@dataclass
class _AliasTarget:
    """Minimal stand-in for a client alias target."""

    client_mac_address: str | None
    client_alias: str | None
    client_id: str | None = None
    client_hostname: str | None = None


@dataclass
class _Registry:
    """Minimal stand-in for the runtime registry."""

    profiles: dict[str, Any] = field(default_factory=dict)
    filters_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    services_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    options_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    endpoints: dict[str, Any] = field(default_factory=dict)
    client_alias_targets: dict[str, Any] = field(default_factory=dict)


def _registry() -> _Registry:
    """Return a registry with two profiles and two endpoints."""
    return _Registry(
        profiles={
            "p-1": SimpleNamespace(name="Default"),
            "p-2": SimpleNamespace(name="Kids"),
        },
        filters_by_profile={
            "p-1": {"ads": SimpleNamespace(enabled=True)},
            "p-2": {"ads": SimpleNamespace(enabled=False)},
        },
        services_by_profile={
            "p-1": {"instagram": SimpleNamespace(current_mode="blocked")},
            "p-2": {"instagram": SimpleNamespace(current_mode="bypassed")},
        },
        options_by_profile={
            "p-1": {
                "safesearch": SimpleNamespace(
                    entity_kind="toggle",
                    is_enabled=True,
                    current_value_key="1",
                ),
                "block_attacks": SimpleNamespace(
                    entity_kind="select",
                    is_enabled=True,
                    current_value_key="high",
                ),
                "unsupported_option": SimpleNamespace(
                    entity_kind="unsupported",
                    is_enabled=False,
                    current_value_key=None,
                ),
            },
        },
        endpoints={
            "ep-1": _Endpoint(name="Firewalla"),
            "ep-2": _Endpoint(name="ctrld-nas"),
        },
        client_alias_targets={
            "aa:bb": _AliasTarget(
                client_mac_address="AA:BB",
                client_alias="Kadens iPad",
                client_id="04070f91bf7d",
                client_hostname="KadensSpyPhone",
            ),
            "cc:dd": _AliasTarget(
                client_mac_address="CC:DD",
                client_alias=None,
                client_id="d18cc9582f25",
                client_hostname="LivingRoomTV",
            ),
            "ee:ff": _AliasTarget(
                client_mac_address="AA:BB",
                client_alias=None,
                client_id="112233445566",
                client_hostname="KadensSpyPhone",
            ),
        },
    )


def _tool_with_registry[ToolT: llm.Tool](tool: ToolT, registry: _Registry) -> ToolT:
    """Point a tool's registry read at a fixed registry.

    Generic in the tool type so the concrete class survives the call: the tests
    below exercise protected hooks that only exist on the subclasses.
    """
    tool._registry = lambda hass: registry  # type: ignore[method-assign]
    return tool


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def test_filter_undo_restores_the_previous_enabled_state() -> None:
    """The undo restores the value read before the write, not the inverse."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    undo = tool._undo(hass, {"filter_id": "ads", "profile_id": "p-1"})

    assert undo == [
        "controld_manager__set_filter_state(filter_id='ads', profile_id='p-1', "
        "enabled=True)"
    ]


async def test_service_undo_emits_one_call_per_service_as_a_label() -> None:
    """Each service gets a call naming its own previous mode, by label."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(SetServiceStateTool(entry_id="e-1"), _registry())

    undo = tool._undo(hass, {"service_id": "instagram"})

    assert undo is not None
    assert len(undo) == 2
    assert "profile_id='p-1', mode='Blocked'" in undo[0]
    assert "profile_id='p-2', mode='Bypassed'" in undo[1]


async def test_option_undo_uses_enabled_for_a_toggle_and_value_for_a_select() -> None:
    """The undo shape follows the option kind, because the schema does."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(SetOptionStateTool(entry_id="e-1"), _registry())

    toggle = tool._undo(hass, {"option_id": "safesearch", "profile_id": "p-1"})
    select = tool._undo(hass, {"option_id": "block_attacks", "profile_id": "p-1"})

    assert toggle == [
        "controld_manager__set_option_state(option_id='safesearch', "
        "profile_id='p-1', enabled=True)"
    ]
    assert select == [
        "controld_manager__set_option_state(option_id='block_attacks', "
        "profile_id='p-1', value='high')"
    ]


async def test_option_undo_is_withheld_when_the_kind_is_unsupported() -> None:
    """An option the integration cannot write also cannot be restored."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(SetOptionStateTool(entry_id="e-1"), _registry())

    assert (
        tool._undo(hass, {"option_id": "unsupported_option", "profile_id": "p-1"})
        is None
    )


async def test_rename_undo_restores_each_endpoints_own_name() -> None:
    """Renaming two endpoints yields two calls, each naming the right old name."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(RenameEndpointTool(entry_id="e-1"), _registry())

    undo = tool._undo(hass, {"endpoint_id": ["ep-1", "ep-2"], "new_name": "Renamed"})

    assert undo == [
        "controld_manager__rename_endpoint(endpoint_id='ep-1', new_name='Firewalla')",
        "controld_manager__rename_endpoint(endpoint_id='ep-2', new_name='ctrld-nas')",
    ]


async def test_rename_undo_skips_an_unknown_endpoint() -> None:
    """A target that is not in the registry has no name to restore."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(RenameEndpointTool(entry_id="e-1"), _registry())

    undo = tool._undo(hass, {"endpoint_id": ["ep-1", "missing"], "new_name": "Renamed"})

    assert undo is not None
    assert len(undo) == 1


async def test_clear_alias_undo_restores_only_clients_that_had_an_alias() -> None:
    """A client with no alias has nothing to restore, so it yields no call."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(ClearClientAliasTool(entry_id="e-1"), _registry())

    undo = tool._undo(hass, {"client_id": ["04070f91bf7d", "d18cc9582f25"]})

    assert undo == [
        "controld_manager__set_client_alias(client_id='04070f91bf7d', "
        "alias='Kadens iPad')"
    ]


async def test_clear_alias_undo_names_the_client_id_not_the_shared_mac() -> None:
    """Two clients share a MAC, so an undo naming the MAC could hit the wrong one."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(ClearClientAliasTool(entry_id="e-1"), _registry())

    undo = tool._undo(hass, {"client_id": "04070f91bf7d"})

    assert undo == [
        "controld_manager__set_client_alias(client_id='04070f91bf7d', "
        "alias='Kadens iPad')"
    ]


async def test_set_alias_undo_clears_by_client_id() -> None:
    """The undo of a set addresses the client the set addressed."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(SetClientAliasTool(entry_id="e-1"), _registry())

    undo = tool._undo(hass, {"client_id": "d18cc9582f25", "alias": "Tablet"})

    assert undo == ["controld_manager__clear_client_alias(client_id='d18cc9582f25')"]


async def test_client_id_beats_a_mac_that_matches_several_clients() -> None:
    """A MAC shared by two clients must not be used when a client id is given."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(SetClientAliasTool(entry_id="e-1"), _registry())

    targets = tool._matching_targets(
        hass, {"client_id": "112233445566", "endpoint_mac": "AA:BB"}
    )

    assert [target.client_id for target in targets] == ["112233445566"]


async def test_alias_matching_falls_back_to_hostname_then_reports_nothing() -> None:
    """Only an explicit selector matches, and an unknown one matches nothing."""
    hass: HomeAssistant = MagicMock()
    tool = _tool_with_registry(SetClientAliasTool(entry_id="e-1"), _registry())

    by_host = tool._matching_targets(hass, {"endpoint_hostname": "LivingRoomTV"})
    unknown = tool._matching_targets(hass, {"client_id": "nope"})

    assert [target.client_id for target in by_host] == ["d18cc9582f25"]
    assert unknown == ()


async def test_a_no_op_write_reports_no_undo() -> None:
    """Nothing changed, so there is nothing to reverse."""
    service_call = AsyncMock()
    fake_hass = MagicMock()
    fake_hass.services.async_call = service_call
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": "p-1", "enabled": True},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    assert result.data["undo"] is None
    service_call.assert_not_called()


async def test_applied_write_reports_the_undo_in_the_result() -> None:
    """The undo reaches the caller on a write that actually happened."""
    service_call = AsyncMock()
    fake_hass = MagicMock()
    fake_hass.services.async_call = service_call
    tool = _tool_with_registry(SetFilterStateTool(entry_id="e-1"), _registry())

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": "p-1", "enabled": False},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["undo"] == [
        "controld_manager__set_filter_state(filter_id='ads', profile_id='p-1', "
        "enabled=True)"
    ]
