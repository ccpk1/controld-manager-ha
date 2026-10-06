"""Tests for the profile id translation in the LLM tools.

The read tools hand the model a Control D profile PK, but the profile services
declare `profile_id` with a Home Assistant device selector. Without a
translation the documented contract is unsatisfiable: a live call with a real PK
failed with "Device ... is not a Control D target", and no tool returns a device
id for the model to use instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import Context
from homeassistant.helpers import llm

from custom_components.controld_manager.llm_tools_control import (
    CreateEndpointTool,
    CreateRuleTool,
    DisableProfileTool,
    SetFilterStateTool,
)
from custom_components.controld_manager.llm_tools_read import (
    GetCatalogTool,
    GetInventoryTool,
)

_PROFILE_PK = "962691chipwa5"
_PROFILE_DEVICE_ID = "1a2b3c4d5e6f7890abcdef1234567890"


@dataclass
class _DeviceManager:
    """Minimal stand-in for the device manager."""

    profile_device_ids: dict[str, str] = field(default_factory=dict)


@dataclass
class _Registry:
    """Minimal stand-in for the runtime registry."""

    profiles: dict[str, Any] = field(default_factory=dict)
    filters_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)


def _hass(service_call: AsyncMock, *, with_device_map: bool = True) -> MagicMock:
    """Return a hass whose config entry exposes a device manager."""
    device_manager = _DeviceManager(
        profile_device_ids={_PROFILE_PK: _PROFILE_DEVICE_ID} if with_device_map else {}
    )
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(
            managers=SimpleNamespace(device=device_manager),
        )
    )
    fake = MagicMock()
    fake.services.async_call = service_call
    fake.config_entries.async_get_entry = MagicMock(return_value=entry)
    return fake


def _llm_context() -> llm.LLMContext:
    """Return a minimal LLM context."""
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=None,
    )


async def test_a_control_tool_sends_the_device_id_not_the_profile_pk() -> None:
    """The service receives the device id its selector expects."""
    service_call = AsyncMock()
    tool = DisableProfileTool(entry_id="e-1")

    await tool.async_call(
        _hass(service_call),
        llm.ToolInput(tool_name=tool.name, tool_args={"profile_id": _PROFILE_PK}),
        _llm_context(),
    )

    sent = service_call.await_args.args[2]
    # Scalar in, scalar out. The caller's shape is preserved so a service that
    # requires exactly one profile (create_endpoint) is not handed a list.
    assert sent["profile_id"] == _PROFILE_DEVICE_ID


async def test_a_control_tool_translates_a_list_of_profile_ids() -> None:
    """Every entry in a list is translated."""
    service_call = AsyncMock()
    tool = DisableProfileTool(entry_id="e-1")

    await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"profile_id": [_PROFILE_PK, "unknown-pk"]},
        ),
        _llm_context(),
    )

    sent = service_call.await_args.args[2]
    # An unmapped value is passed through so the service reports it properly.
    assert sent["profile_id"] == [_PROFILE_DEVICE_ID, "unknown-pk"]


async def test_an_unmapped_profile_pk_is_passed_through_unchanged() -> None:
    """Without a device mapping the value is left alone rather than dropped."""
    service_call = AsyncMock()
    tool = DisableProfileTool(entry_id="e-1")

    await tool.async_call(
        _hass(service_call, with_device_map=False),
        llm.ToolInput(tool_name=tool.name, tool_args={"profile_id": _PROFILE_PK}),
        _llm_context(),
    )

    sent = service_call.await_args.args[2]
    assert sent["profile_id"] == _PROFILE_PK


async def test_creating_an_endpoint_sends_a_single_profile_not_a_list() -> None:
    """create_endpoint takes one profile as a string, so translation must not wrap.

    The composed tool-to-service path is what failed here: the translation helper
    returned a list while the create schema required a string, so every create
    call was rejected with "value should be a string at 'profile_id'".
    """
    service_call = AsyncMock()
    tool = CreateEndpointTool(entry_id="e-1")

    await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "endpoint_name": "Kitchen Tablet",
                "profile_id": _PROFILE_PK,
            },
        ),
        _llm_context(),
    )

    sent = service_call.await_args.args[2]
    assert sent["profile_id"] == _PROFILE_DEVICE_ID
    assert isinstance(sent["profile_id"], str)


async def test_the_precheck_still_reads_the_registry_by_profile_pk() -> None:
    """Translation applies to the service call only, not the pre-write read.

    The registry is keyed by the Control D profile PK, so translating before the
    pre-check would make it look up a device id and silently miss.
    """
    service_call = AsyncMock()
    tool = SetFilterStateTool(entry_id="e-1")
    registry = _Registry(
        profiles={_PROFILE_PK: SimpleNamespace(name="Developer Testing")},
        filters_by_profile={_PROFILE_PK: {"ads": SimpleNamespace(enabled=True)}},
    )
    tool._registry = lambda _hass: registry  # type: ignore[method-assign]

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": _PROFILE_PK, "enabled": True},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "already_in_state"
    assert result.data["before"] == {"enabled": [True]}
    service_call.assert_not_called()


async def test_get_catalog_translates_the_profile_id() -> None:
    """get_catalog is the one read tool whose service needs a device id."""
    service_call = AsyncMock()
    service_call.return_value = {"items": []}
    tool = GetCatalogTool(entry_id="e-1")

    await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"catalog_type": "filters", "profile_id": _PROFILE_PK},
        ),
        _llm_context(),
    )

    sent = service_call.await_args.args[2]
    assert sent["profile_id"] == [_PROFILE_DEVICE_ID]


async def test_get_inventory_passes_the_profile_pk_through() -> None:
    """get_inventory's service takes the Control D PK directly, so it is untouched."""
    service_call = AsyncMock()
    service_call.return_value = {"profiles": []}
    tool = GetInventoryTool(entry_id="e-1")

    await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"detail": "summary", "profile_id": _PROFILE_PK},
        ),
        _llm_context(),
    )

    sent = service_call.await_args.args[2]
    assert sent["profile_id"] == _PROFILE_PK


@pytest.mark.parametrize(
    ("tool_class", "args"),
    [
        (GetCatalogTool, {"catalog_type": "filters"}),
        (GetInventoryTool, {"detail": "summary"}),
    ],
    ids=["get_catalog", "get_inventory"],
)
async def test_a_call_without_a_profile_scope_is_unchanged(
    tool_class: type[llm.Tool], args: dict[str, Any]
) -> None:
    """A read with no profile selector is not rewritten."""
    service_call = AsyncMock()
    service_call.return_value = {"items": []}
    tool = tool_class(entry_id="e-1")

    await tool.async_call(
        _hass(service_call),
        llm.ToolInput(tool_name=tool.name, tool_args=args),
        _llm_context(),
    )

    sent = service_call.await_args.args[2]
    assert "profile_id" not in sent


async def test_an_unreadable_precheck_is_reported_as_a_warning() -> None:
    """A write that could not read the prior state must say so.

    Observed live: addressing a profile by a value the registry cannot resolve
    made the pre-check return nothing, so the tool reported `changed: true` when
    the filter was already disabled and nothing actually changed.
    """
    service_call = AsyncMock()
    tool = SetFilterStateTool(entry_id="e-1")
    # A registry whose profiles are keyed differently, so nothing resolves.
    tool._registry = lambda _hass: _Registry(profiles={})  # type: ignore[method-assign]

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={
                "filter_id": "games",
                "profile_id": "unknown-profile",
                "enabled": False,
            },
        ),
        _llm_context(),
    )

    assert result.data["before"] is None
    assert result.data["undo"] is None
    assert len(result.data["warnings"]) == 1
    assert "could not be read" in result.data["warnings"][0]
    service_call.assert_called_once()


async def test_a_resolved_write_carries_no_warning() -> None:
    """When the prior state is readable the result is fully qualified."""
    service_call = AsyncMock()
    tool = SetFilterStateTool(entry_id="e-1")
    registry = _Registry(
        profiles={_PROFILE_PK: SimpleNamespace(name="Developer Testing")},
        filters_by_profile={_PROFILE_PK: {"ads": SimpleNamespace(enabled=True)}},
    )
    tool._registry = lambda _hass: registry  # type: ignore[method-assign]

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"filter_id": "ads", "profile_id": _PROFILE_PK, "enabled": False},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["before"] == {"enabled": [True]}
    assert result.data["undo"] is not None
    assert result.data["warnings"] == []


async def test_create_rule_is_not_warned_for_having_no_precheck() -> None:
    """`create_rule` cannot read a prior state by design, so it must not warn."""
    service_call = AsyncMock()
    tool = CreateRuleTool(entry_id="e-1")

    result = await tool.async_call(
        _hass(service_call),
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"hostname": "example.com"},
        ),
        _llm_context(),
    )

    assert result.data["status"] == "applied"
    assert result.data["warnings"] == []
    assert result.data["undo"] is not None
