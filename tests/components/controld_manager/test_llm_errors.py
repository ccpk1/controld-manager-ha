"""Error-path tests for the LLM tools.

An MCP client can call a tool directly, bypassing the provider's validation, so a
malformed call must produce a clean error rather than a bare ``KeyError``. These
tests drive each failure mode through the tool layer.
"""

from __future__ import annotations

from typing import Final
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm

from custom_components.controld_manager.const import (
    CONF_API_TOKEN,
    CONF_LLM_TOOL_MODE,
    DOMAIN,
    LLM_TOOL_MODE_FULL,
    LLM_TOOL_MODE_READ_ONLY,
)
from custom_components.controld_manager.llm_tools_common import PROMPT

_FIRST_REFRESH: Final = (
    "custom_components.controld_manager.coordinator."
    "ControlDManagerDataUpdateCoordinator.async_config_entry_first_refresh"
)
_PREDICATE: Final = (
    "custom_components.controld_manager.helpers.llm_support.llm_tools_supported"
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


async def _tools(hass: HomeAssistant, mode: str) -> dict[str, llm.Tool]:
    """Register one entry at the given tier and return its tools by name."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    return {tool.name: tool for tool in api_instance.tools}


@pytest.fixture(name="read_tools")
async def read_tools_fixture(hass: HomeAssistant) -> dict[str, llm.Tool]:
    """Return the read-tier tools by name."""
    return await _tools(hass, LLM_TOOL_MODE_READ_ONLY)


@pytest.fixture(name="control_tools")
async def control_tools_fixture(hass: HomeAssistant) -> dict[str, llm.Tool]:
    """Return the Full-tier tools by name."""
    return await _tools(hass, LLM_TOOL_MODE_FULL)


async def test_missing_required_argument_is_not_a_key_error(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """A required argument that is absent must fail as validation, not KeyError."""
    tool = read_tools[f"{DOMAIN}__test_domain"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_partially_missing_arguments_are_rejected(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """Supplying only part of the required set is still a clean failure."""
    tool = read_tools[f"{DOMAIN}__test_domain"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={"endpoint_id": "ep-1"}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_unknown_argument_is_rejected(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """An argument the schema does not declare must not be silently accepted."""
    tool = read_tools[f"{DOMAIN}__get_account_overview"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={"not_a_real_field": 1}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_invalid_enum_value_is_rejected(
    hass: HomeAssistant, control_tools: dict[str, llm.Tool]
) -> None:
    """An out-of-range enum value fails validation before any service call."""
    service_call = AsyncMock()
    tool = control_tools[f"{DOMAIN}__set_filter_state"]
    fake_hass = MagicMock()
    fake_hass.services.async_call = service_call

    with pytest.raises(Exception) as err:
        await tool.async_call(
            fake_hass,
            llm.ToolInput(
                tool_name=tool.name,
                tool_args={"filter_id": "ads", "enabled": "maybe"},
            ),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)
    service_call.assert_not_called()


async def test_an_out_of_range_page_size_is_rejected(
    hass: HomeAssistant, read_tools: dict[str, llm.Tool]
) -> None:
    """A page size beyond the documented maximum fails rather than being sent."""
    tool = read_tools[f"{DOMAIN}__get_activity_log"]

    with pytest.raises(Exception) as err:
        await tool.async_call(
            hass,
            llm.ToolInput(tool_name=tool.name, tool_args={"page_size": 5000}),
            _llm_context(),
        )

    assert not isinstance(err.value, KeyError)


async def test_a_service_failure_is_reported_as_failed(
    hass: HomeAssistant, control_tools: dict[str, llm.Tool]
) -> None:
    """A rejected write returns a failed action result instead of raising."""
    from homeassistant.exceptions import HomeAssistantError

    tool = control_tools[f"{DOMAIN}__disable_profile"]
    # Model an unreadable registry so the pre-check proceeds to the write.
    tool._registry = lambda _hass: None  # type: ignore[method-assign]
    fake_hass = MagicMock()
    fake_hass.services.async_call = AsyncMock(
        side_effect=HomeAssistantError("rejected")
    )

    result = await tool.async_call(
        fake_hass,
        llm.ToolInput(tool_name=tool.name, tool_args={"profile_id": "p-1"}),
        _llm_context(),
    )

    assert result.error is True
    assert result.data["status"] == "failed"
    assert result.data["changed"] is False
    assert result.data["after"] is None


def test_prompt_covers_the_shipped_surface() -> None:
    """The prompt must describe the tools that actually exist.

    It is served on every request, so a stale prompt teaches the model about
    tools it cannot call. These are the concepts it must carry.
    """
    required = {
        "profile",
        "endpoint",
        "client",
        "already_in_state",
        "truncated",
        "undo",
        "retention",
        "triggerValue",
        "get_account_overview",
        "get_activity_log",
        "test_domain",
        "untrusted",
    }
    missing = {term for term in required if term.lower() not in PROMPT.lower()}
    assert missing == set(), f"prompt is missing: {sorted(missing)}"


def test_prompt_does_not_describe_removed_tools() -> None:
    """The ranked analytics tools were dropped, so the prompt must not imply them."""
    for removed in (
        "get_block_breakdown",
        "get_top_blocked_domains",
        "get_block_summary",
        "get_policy",
    ):
        assert removed not in PROMPT
