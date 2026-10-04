"""Contract tests for every registered LLM tool.

These assert the shared spec in ``docs/MCP_TOOL_REFERENCE.md`` against the tools
as they are actually registered, so the surface cannot drift from its contract.
"""

from __future__ import annotations

import json
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    CONF_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_OFF,
    LLM_TOOL_MODE_READ_AND_CONTROL,
    LLM_TOOL_MODE_READ_ONLY,
    LLM_TOOL_MODE_SUMMARY_ONLY,
    SERVICE_FIELD_CONFIG_ENTRY_ID,
)

_FIRST_REFRESH: Final = (
    "custom_components.controld_manager.coordinator."
    "ControlDManagerDataUpdateCoordinator.async_config_entry_first_refresh"
)
_PREDICATE: Final = (
    "custom_components.controld_manager.helpers.llm_support.llm_tools_supported"
)

# The read surface delivered by Phase 2. Control tools land in Phase 3.
_READ_TOOLS: Final = frozenset(
    {
        "get_account_overview",
        "get_inventory",
        "get_activity_log",
        "test_domain",
        "get_catalog",
    }
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


async def _tools(hass: HomeAssistant, mode: str) -> list[llm.Tool]:
    """Register one entry at the given tier and return its tools."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Control D",
        data={CONF_API_TOKEN: "token-value"},
        options={CONF_LLM_TOOL_MODE: mode},
        unique_id="user-123",
    )
    entry.add_to_hass(hass)
    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        api_instance = await llm.async_get_api(
            hass, f"{DOMAIN}-{entry.entry_id}", _llm_context()
        )
    return list(api_instance.tools)


@pytest.fixture(name="read_tools")
async def read_tools_fixture(hass: HomeAssistant) -> list[llm.Tool]:
    """Return the tools registered at the read tier."""
    return await _tools(hass, LLM_TOOL_MODE_READ_ONLY)


async def test_read_tier_registers_exactly_the_read_surface(
    read_tools: list[llm.Tool],
) -> None:
    """The read tier exposes the Phase 2 tools and nothing else."""
    assert {tool.name for tool in read_tools} == {
        f"{DOMAIN}__{name}" for name in _READ_TOOLS
    }


async def test_every_tool_name_is_namespaced(read_tools: list[llm.Tool]) -> None:
    """Tool names carry the integration prefix so merged APIs stay unambiguous."""
    for tool in read_tools:
        assert tool.name.startswith(f"{DOMAIN}__"), tool.name


async def test_every_tool_declares_its_integration(read_tools: list[llm.Tool]) -> None:
    """A tool without `integration` is deprecated by Home Assistant."""
    for tool in read_tools:
        assert tool.integration == DOMAIN, tool.name


async def test_every_tool_has_a_title_and_description(
    read_tools: list[llm.Tool],
) -> None:
    """Both are served to clients; an empty one leaves the model guessing."""
    for tool in read_tools:
        assert tool.title, tool.name
        assert tool.description, tool.name
        assert len(tool.description) > 80, tool.name


async def test_every_read_tool_declares_all_four_annotations(
    read_tools: list[llm.Tool],
) -> None:
    """Annotation defaults are the least safe case, so reads must be explicit."""
    for tool in read_tools:
        annotations = tool.annotations
        assert annotations is not None, tool.name
        assert annotations.read_only is True, tool.name
        assert annotations.destructive is False, tool.name
        assert annotations.idempotent is True, tool.name
        assert annotations.open_world is False, tool.name


async def test_every_parameter_is_described(read_tools: list[llm.Tool]) -> None:
    """Field guidance reaches the client through the schema marker description."""
    missing: list[str] = []
    for tool in read_tools:
        for marker in tool.parameters.schema:
            if not getattr(marker, "description", None):
                missing.append(f"{tool.name}:{marker.schema}")
    assert missing == [], f"parameters without a description: {missing}"


async def test_tools_never_expose_the_config_entry_selector(
    read_tools: list[llm.Tool],
) -> None:
    """The tool binds its own entry, so the model never picks an account."""
    for tool in read_tools:
        assert SERVICE_FIELD_CONFIG_ENTRY_ID not in tool.parameters.schema, tool.name


@pytest.mark.parametrize(
    "mode",
    [
        LLM_TOOL_MODE_SUMMARY_ONLY,
        LLM_TOOL_MODE_READ_ONLY,
        LLM_TOOL_MODE_READ_AND_CONTROL,
    ],
)
async def test_summary_exposes_only_the_overview(
    hass: HomeAssistant, mode: str
) -> None:
    """Summary stays the narrow tier; every read tier gets the full read set."""
    tools = await _tools(hass, mode)
    if mode == LLM_TOOL_MODE_SUMMARY_ONLY:
        assert {tool.name for tool in tools} == {f"{DOMAIN}__get_account_overview"}
    else:
        assert {tool.name for tool in tools} == {
            f"{DOMAIN}__{name}" for name in _READ_TOOLS
        }


async def test_off_tier_exposes_no_api(hass: HomeAssistant) -> None:
    """The Off tier registers nothing at all."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Control D",
        data={CONF_API_TOKEN: "token-value"},
        options={CONF_LLM_TOOL_MODE: LLM_TOOL_MODE_OFF},
        unique_id="user-123",
    )
    entry.add_to_hass(hass)
    with (
        patch(_FIRST_REFRESH, new=AsyncMock()),
        patch(_PREDICATE, return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert not [
        api for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}-")
    ]


async def test_tool_result_envelope_is_json_serializable(
    hass: HomeAssistant, read_tools: list[llm.Tool]
) -> None:
    """MCP serves the envelope as JSON text, so it must serialize cleanly."""
    overview = next(
        tool for tool in read_tools if tool.name == f"{DOMAIN}__get_account_overview"
    )
    result = await overview.async_call(
        hass,
        llm.ToolInput(tool_name=overview.name, tool_args={}),
        _llm_context(),
    )
    assert json.dumps(result.data)


async def test_a_missing_required_argument_is_a_clean_error(
    hass: HomeAssistant, read_tools: list[llm.Tool]
) -> None:
    """An MCP client can call directly, so a bad call must not raise KeyError."""
    test_domain = next(
        tool for tool in read_tools if tool.name == f"{DOMAIN}__test_domain"
    )
    with pytest.raises(Exception) as err:
        await test_domain.async_call(
            hass,
            llm.ToolInput(tool_name=test_domain.name, tool_args={}),
            _llm_context(),
        )
    assert not isinstance(err.value, KeyError)
